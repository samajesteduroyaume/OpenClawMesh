"""
Protocole Pub/Sub Épidémique GossipSub v1.1 pour OpenClawMesh.

Inspiré de Libp2p GossipSub :
- Routage par Topic décentralisé (ex: 'openclaw/v1/discovery', 'openclaw/v1/skills', 'openclaw/v1/metrics')
- Formation et auto-stabilisation dynamique du maillage (Mesh D, D_low, D_high, GRAFT, PRUNE)
- Double dissémination : Eager Push vers les pairs du maillage topic + Lazy Gossip (IHAVE / IWANT)
- Scoring de réputation et résistance aux attaques Sybil / Spam
- Déduplication de messages par cache d'identifiants SHA-256
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import random
import time
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from ..config import get_settings

logger = logging.getLogger("openclaw_mesh.gossipsub")
_settings = get_settings()

_GOSSIPSUB_SIGNATURE_FIELD = "_sig"
_DEFAULT_TOPIC_DISCOVERY = "openclaw/v1/discovery"
_DEFAULT_TOPIC_METRICS = "openclaw/v1/metrics"
_DEFAULT_TOPIC_SKILLS = "openclaw/v1/skills"


@dataclass
class GossipMessage:
    """Message d'application diffusé sur un topic GossipSub."""

    topic: str
    data: dict[str, Any]
    from_peer: str
    seq: int
    msg_id: str = ""
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.msg_id:
            self.msg_id = self.compute_id(self.topic, self.from_peer, self.seq, self.data)

    @staticmethod
    def compute_id(topic: str, from_peer: str, seq: int, data: dict[str, Any]) -> str:
        """Calcule un identifiant déterministe unique SHA-256 pour le message."""
        raw = f"{topic}|{from_peer}|{seq}|{json.dumps(data, sort_keys=True, separators=(',', ':'))}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GossipMessage:
        return cls(
            topic=str(d.get("topic", "")),
            data=dict(d.get("data", {})),
            from_peer=str(d.get("from_peer", "")),
            seq=int(d.get("seq", 0)),
            msg_id=str(d.get("msg_id", "")),
            timestamp=float(d.get("timestamp", time.time())),
        )


@dataclass
class ControlMessage:
    """Messages de contrôle du maillage GossipSub (GRAFT, PRUNE, IHAVE, IWANT)."""

    graft: list[str] = field(default_factory=list)  # topics to graft
    prune: list[str] = field(default_factory=list)  # topics to prune
    ihave: list[dict[str, Any]] = field(default_factory=list)  # [{"topic": t, "msg_ids": [...]}]
    iwant: list[str] = field(default_factory=list)  # [msg_id_1, msg_id_2, ...]

    def is_empty(self) -> bool:
        return not (self.graft or self.prune or self.ihave or self.iwant)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ControlMessage:
        return cls(
            graft=list(d.get("graft", [])),
            prune=list(d.get("prune", [])),
            ihave=list(d.get("ihave", [])),
            iwant=list(d.get("iwant", [])),
        )


class MessageCache:
    """Cache à fenêtre glissante pour l'historique des messages récents (mcache)."""

    def __init__(self, history_length: int = 5, gossip_window: int = 3):
        self.history_length = history_length
        self.gossip_window = gossip_window
        self.history: list[dict[str, GossipMessage]] = [{} for _ in range(history_length)]
        self.msg_lookup: dict[str, GossipMessage] = {}

    def put(self, msg: GossipMessage) -> None:
        self.history[0][msg.msg_id] = msg
        self.msg_lookup[msg.msg_id] = msg

    def get(self, msg_id: str) -> GossipMessage | None:
        return self.msg_lookup.get(msg_id)

    def get_gossip_msg_ids(self, topic: str) -> list[str]:
        """Retourne les identifiants de messages dans la fenêtre de gossip pour ce topic."""
        ids: list[str] = []
        for i in range(min(self.gossip_window, len(self.history))):
            ids.extend([msg.msg_id for msg in self.history[i].values() if msg.topic == topic])
        return ids

    def shift(self) -> None:
        """Fait glisser la fenêtre d'historique lors de chaque heartbeat."""
        popped = self.history.pop()
        for msg_id in popped:
            # Si plus présent dans les fenêtres plus récentes, libérer la mémoire
            still_present = any(msg_id in bucket for bucket in self.history)
            if not still_present:
                self.msg_lookup.pop(msg_id, None)
        self.history.insert(0, {})


class GossipSubNode:
    """
    Nœud de routage pub/sub décentralisé GossipSub v1.1.

    Permet la diffusion temps réel tolérante aux pannes sans aucun coordinateur central.
    """

    def __init__(
        self,
        node_id: str,
        node_name: str = "openclaw-gossipsub",
        psk: str | None = None,
        d: int = 6,
        d_low: int = 4,
        d_high: int = 12,
        d_lazy: int = 6,
        heartbeat_interval: float = 1.0,
        send_fn: Callable[[str, dict[str, Any]], Any] | None = None,
    ):
        self.node_id = node_id
        self.node_name = node_name
        self.psk = psk or _settings.psk
        self.d = d
        self.d_low = d_low
        self.d_high = d_high
        self.d_lazy = d_lazy
        self.heartbeat_interval = heartbeat_interval
        self.send_fn = send_fn

        # Subscriptions locales: topic -> Set[Callback(GossipMessage)]
        self.subscriptions: dict[str, set[Callable[[GossipMessage], None]]] = defaultdict(set)

        # Topologie de maillage: topic -> Set[peer_id]
        self.mesh: dict[str, set[str]] = defaultdict(set)

        # Tous les pairs connus intéressés par un topic: topic -> Set[peer_id]
        self.topic_peers: dict[str, set[str]] = defaultdict(set)

        # Table des adresses des pairs : peer_id -> endpoint (ex: "udp://1.2.3.4:8775" ou "ws://...")
        self.peer_endpoints: dict[str, str] = {}

        # Scores de pairs : peer_id -> float
        self.peer_scores: dict[str, float] = defaultdict(lambda: 10.0)

        # Backoff pour les prunes : (topic, peer_id) -> expire_timestamp
        self.prune_backoff: dict[tuple[str, str], float] = {}

        # Cache de déduplication et de recherche
        self.seen_messages: OrderedDict[str, float] = OrderedDict()
        self.mcache = MessageCache(
            history_length=_settings.gossipsub_history_length,
            gossip_window=_settings.gossipsub_history_gossip,
        )

        self._seq = 0
        self._running = False
        self._heartbeat_task: asyncio.Task | None = None

    def add_peer(self, peer_id: str, endpoint: str) -> None:
        """Enregistre un pair et son adresse réseau."""
        if peer_id != self.node_id:
            self.peer_endpoints[peer_id] = endpoint
            for topic in list(self.subscriptions.keys()):
                self.topic_peers[topic].add(peer_id)
                if len(self.mesh[topic]) < self.d:
                    self.mesh[topic].add(peer_id)

    def remove_peer(self, peer_id: str) -> None:
        """Supprime un pair déconnecté de tous les maillages."""
        self.peer_endpoints.pop(peer_id, None)
        self.peer_scores.pop(peer_id, None)
        for peers in self.mesh.values():
            peers.discard(peer_id)
        for peers in self.topic_peers.values():
            peers.discard(peer_id)

    # ------------------------------------------------------------------ #
    # Souscription & Publication
    # ------------------------------------------------------------------ #
    def subscribe(self, topic: str, handler: Callable[[GossipMessage], None] | None = None) -> None:
        """S'abonne à un topic de diffusion et initialise le maillage si nécessaire."""
        if handler:
            self.subscriptions[topic].add(handler)
        else:
            _ = self.subscriptions[topic]

        # Greffe immédiate si des pairs sont déjà connus
        if topic not in self.mesh:
            self.mesh[topic] = set()
            available = list(
                (self.topic_peers.get(topic, set()) | set(self.peer_endpoints.keys()))
                - {self.node_id}
            )
            random.shuffle(available)
            for p in available[: self.d]:
                self.mesh[topic].add(p)
                self.topic_peers[topic].add(p)
                self._send_control_sync(p, ControlMessage(graft=[topic]))

    def unsubscribe(self, topic: str) -> None:
        """Se désabonne d'un topic et élague les pairs du maillage."""
        self.subscriptions.pop(topic, None)
        peers_to_prune = list(self.mesh.pop(topic, set()))
        for p in peers_to_prune:
            self._send_control_sync(p, ControlMessage(prune=[topic]))

    async def publish(self, topic: str, data: dict[str, Any]) -> str:
        """
        Publie un message sur un topic.
        - Eager push immédiat vers tous les pairs du mesh[topic].
        - Enregistrement dans le message cache pour les annonces IHAVE ultérieures.
        """
        self._seq += 1
        msg = GossipMessage(
            topic=topic,
            data=data,
            from_peer=self.node_id,
            seq=self._seq,
        )
        self._mark_seen(msg.msg_id)
        self.mcache.put(msg)

        # Délivrer localement si souscrit
        self._deliver_local(msg)

        # Eager push vers les pairs du maillage
        mesh_peers = self.mesh.get(topic, set())
        fanout_peers = set(mesh_peers)
        if not fanout_peers:
            available = list(
                (self.topic_peers.get(topic, set()) | set(self.peer_endpoints.keys()))
                - {self.node_id}
            )
            if available:
                fanout_peers = set(random.sample(available, min(self.d, len(available))))

        wire_msg = self._pack_wire_message(messages=[msg])
        for peer_id in fanout_peers:
            endpoint = self.peer_endpoints.get(peer_id)
            if endpoint and self.send_fn:
                try:
                    res = self.send_fn(endpoint, wire_msg)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as exc:
                    logger.debug(f"Erreur envoi publish GossipSub vers {peer_id}: {exc}")

        return msg.msg_id

    # ------------------------------------------------------------------ #
    # Réception et Traitement
    # ------------------------------------------------------------------ #
    def _mark_seen(self, msg_id: str) -> bool:
        """Retourne True si le message est nouveau, False si déjà vu."""
        if msg_id in self.seen_messages:
            return False
        self.seen_messages[msg_id] = time.time()
        while len(self.seen_messages) > 10000:
            self.seen_messages.popitem(last=False)
        return True

    def _deliver_local(self, msg: GossipMessage) -> None:
        handlers = self.subscriptions.get(msg.topic, set())
        for h in handlers:
            try:
                h(msg)
            except Exception as e:
                logger.warning(f"Erreur handler topic {msg.topic}: {e}")

    async def handle_incoming(self, raw_payload: dict[str, Any], sender_endpoint: str) -> None:
        """Point d'entrée pour traiter tout paquet GossipSub reçu."""
        if not isinstance(raw_payload, dict) or raw_payload.get("type") != "gossipsub_v1":
            return

        # Vérification d'authentification HMAC si configuré
        if self.psk:
            sig = raw_payload.get(_GOSSIPSUB_SIGNATURE_FIELD)
            unsigned = {k: v for k, v in raw_payload.items() if k != _GOSSIPSUB_SIGNATURE_FIELD}
            expected = hmac.new(
                self.psk.encode("utf-8"),
                json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not sig or not hmac.compare_digest(expected, sig):
                logger.warning(f"Paquet GossipSub rejeté de {sender_endpoint} : signature invalide")
                return

        from_peer = str(raw_payload.get("sender_id", ""))
        if from_peer and from_peer != self.node_id:
            self.add_peer(from_peer, sender_endpoint)

        # 1. Traitement des messages d'application
        msgs_raw = raw_payload.get("messages", [])
        for m_dict in msgs_raw:
            try:
                msg = GossipMessage.from_dict(m_dict)
            except Exception:
                continue

            if self._mark_seen(msg.msg_id):
                self.mcache.put(msg)
                self.peer_scores[from_peer] += 0.1  # Bonus pour livraison valide

                # Mémoriser que ce pair connaît ce topic
                self.topic_peers[msg.topic].add(from_peer)

                # Délivrer localement
                self._deliver_local(msg)

                # Relayer (Eager forward) aux autres pairs du maillage pour ce topic
                forward_targets = self.mesh.get(msg.topic, set()) - {from_peer, self.node_id}
                if forward_targets:
                    fwd_wire = self._pack_wire_message(messages=[msg])
                    for target_id in forward_targets:
                        target_ep = self.peer_endpoints.get(target_id)
                        if target_ep and self.send_fn:
                            try:
                                res = self.send_fn(target_ep, fwd_wire)
                                if asyncio.iscoroutine(res):
                                    await res
                            except Exception:
                                pass

        # 2. Traitement des messages de contrôle
        ctrl_dict = raw_payload.get("control")
        if ctrl_dict:
            try:
                ctrl = ControlMessage.from_dict(ctrl_dict)
                await self._handle_control(from_peer, ctrl)
            except Exception as e:
                logger.debug(f"Erreur traitement control GossipSub: {e}")

    async def _handle_control(self, from_peer: str, ctrl: ControlMessage) -> None:
        """Traite les instructions de contrôle GRAFT, PRUNE, IHAVE, IWANT."""
        # GRAFT: Pair souhaite rejoindre notre maillage
        for topic in ctrl.graft:
            self.topic_peers[topic].add(from_peer)
            if topic in self.subscriptions:
                self.mesh[topic].add(from_peer)

        # PRUNE: Pair souhaite quitter notre maillage
        for topic in ctrl.prune:
            if topic in self.mesh:
                self.mesh[topic].discard(from_peer)
            # Enregistrer le backoff pour éviter de le re-greffer immédiatement
            self.prune_backoff[(topic, from_peer)] = time.time() + 30.0

        # IHAVE: Pair annonce des identifiants de messages qu'il possède
        missing_ids: list[str] = []
        for item in ctrl.ihave:
            topic = item.get("topic", "")
            if topic in self.subscriptions:
                missing_ids.extend([
                    mid for mid in item.get("msg_ids", []) if mid not in self.seen_messages
                ])

        if missing_ids:
            # Répondre par IWANT
            await self._send_control_async(from_peer, ControlMessage(iwant=missing_ids))

        # IWANT: Pair demande des messages complets
        if ctrl.iwant:
            to_send: list[GossipMessage] = []
            for mid in ctrl.iwant:
                cached_msg = self.mcache.get(mid)
                if cached_msg:
                    to_send.append(cached_msg)
            if to_send:
                wire_msg = self._pack_wire_message(messages=to_send)
                ep = self.peer_endpoints.get(from_peer)
                if ep and self.send_fn:
                    try:
                        res = self.send_fn(ep, wire_msg)
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception:
                        pass

    # ------------------------------------------------------------------ #
    # Heartbeat & Auto-stabilisation du Maillage
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        """Démarre la boucle asynchrone de pulsation Heartbeat."""
        if self._running:
            return
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(
            f"✓ GossipSub v1.1 actif pour '{self.node_name}' (D={self.d}, D_low={self.d_low}, D_high={self.d_high})"
        )

    async def stop(self) -> None:
        """Arrête la pulsation."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._run_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Erreur heartbeat GossipSub: {e}")

    async def _run_heartbeat(self) -> None:
        """Exécute un cycle d'auto-stabilisation et d'émission de potins (IHAVE)."""
        now = time.time()

        # 1. Maintenance du maillage pour chaque topic souscrit
        for topic in list(self.subscriptions.keys()):
            current_mesh = self.mesh[topic]

            # Nettoyer les pairs déconnectés
            dead_peers = {p for p in current_mesh if p not in self.peer_endpoints}
            current_mesh -= dead_peers

            # Si |mesh| < D_low : Greffer (GRAFT) de nouveaux pairs
            if len(current_mesh) < self.d_low:
                candidates = list(
                    (self.topic_peers.get(topic, set()) | set(self.peer_endpoints.keys()))
                    - current_mesh
                    - {self.node_id}
                )
                valid_candidates = [
                    c for c in candidates if self.prune_backoff.get((topic, c), 0) < now
                ]
                valid_candidates.sort(key=lambda p: self.peer_scores[p], reverse=True)
                needed = self.d - len(current_mesh)
                to_graft = valid_candidates[:needed]

                for p in to_graft:
                    current_mesh.add(p)
                    self.topic_peers[topic].add(p)
                    await self._send_control_async(p, ControlMessage(graft=[topic]))

            # Si |mesh| > D_high : Élaguer (PRUNE) les pairs excédentaires (les moins bien notés)
            elif len(current_mesh) > self.d_high:
                sorted_peers = sorted(current_mesh, key=lambda p: self.peer_scores[p])
                excess = len(current_mesh) - self.d
                to_prune = sorted_peers[:excess]

                for p in to_prune:
                    current_mesh.remove(p)
                    await self._send_control_async(p, ControlMessage(prune=[topic]))

            # 2. Émission Lazy Gossip (IHAVE) vers les pairs hors maillage
            gossip_ids = self.mcache.get_gossip_msg_ids(topic)
            if gossip_ids:
                non_mesh_peers = list(
                    (self.topic_peers.get(topic, set()) | set(self.peer_endpoints.keys()))
                    - current_mesh
                    - {self.node_id}
                )
                if non_mesh_peers:
                    selected_targets = random.sample(
                        non_mesh_peers, min(self.d_lazy, len(non_mesh_peers))
                    )
                    for target_peer in selected_targets:
                        ctrl = ControlMessage(ihave=[{"topic": topic, "msg_ids": gossip_ids}])
                        await self._send_control_async(target_peer, ctrl)

        # 3. Décalage de la fenêtre de cache mcache
        self.mcache.shift()

    # ------------------------------------------------------------------ #
    # Envoi & Empaquetage Wire
    # ------------------------------------------------------------------ #
    def _pack_wire_message(
        self,
        messages: list[GossipMessage] | None = None,
        control: ControlMessage | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "gossipsub_v1",
            "sender_id": self.node_id,
            "sender_name": self.node_name,
            "ts": time.time(),
            "messages": [m.to_dict() for m in (messages or [])],
        }
        if control and not control.is_empty():
            payload["control"] = control.to_dict()

        if self.psk:
            unsigned = {k: v for k, v in payload.items() if k != _GOSSIPSUB_SIGNATURE_FIELD}
            canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
            payload[_GOSSIPSUB_SIGNATURE_FIELD] = hmac.new(
                self.psk.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
            ).hexdigest()

        return payload

    async def _send_control_async(self, target_peer_id: str, control: ControlMessage) -> None:
        endpoint = self.peer_endpoints.get(target_peer_id)
        if endpoint and self.send_fn:
            wire_msg = self._pack_wire_message(control=control)
            try:
                res = self.send_fn(endpoint, wire_msg)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.debug(f"Erreur envoi control vers {target_peer_id}: {e}")

    def _send_control_sync(self, target_peer_id: str, control: ControlMessage) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._send_control_async(target_peer_id, control))
        except RuntimeError:
            pass
