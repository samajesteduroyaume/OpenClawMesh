"""
Protocole Gossip (Épidémique) pour la diffusion des métriques de nœuds OpenClawMesh.

Permet à chaque nœud d'annoncer et de synchroniser en temps réel la charge matérielle
(CPU, RAM, VRAM libre, nombre de tâches en cours) et la disponibilité du cluster
sans inonder le réseau ni centraliser l'état.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import random
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from ..config import get_settings

logger = logging.getLogger("openclaw_mesh.gossip")
_settings = get_settings()

_GOSSIP_SIGNATURE_FIELD = "_sig"
_DEFAULT_FANOUT = 3
_DEFAULT_GOSSIP_INTERVAL = 5.0
_METRICS_TTL = 60.0  # Expire un nœud silencieux après 60s


@dataclass
class NodeMetrics:
    """Métriques en temps réel d'un nœud du maillage."""

    node_name: str
    node_id: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    vram_free_mb: int = 0
    active_tasks: int = 0
    capacity: int = 10
    skills: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    endpoint: str | None = None
    reputation_score: float = 1.0

    def is_stale(self, ttl: float = _METRICS_TTL) -> bool:
        return (time.time() - self.timestamp) > ttl

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeMetrics:
        return cls(
            node_name=str(data.get("node_name", "unknown")),
            node_id=str(data.get("node_id", "")),
            cpu_percent=float(data.get("cpu_percent", 0.0)),
            memory_percent=float(data.get("memory_percent", 0.0)),
            vram_free_mb=int(data.get("vram_free_mb", 0)),
            active_tasks=int(data.get("active_tasks", 0)),
            capacity=int(data.get("capacity", 10)),
            skills=list(data.get("skills", [])),
            timestamp=float(data.get("timestamp", time.time())),
            endpoint=data.get("endpoint"),
            reputation_score=float(data.get("reputation_score", 1.0)),
        )


class GossipProtocol:
    """Gestionnaire de dissémination Gossip / Rumor-Mongering."""

    def __init__(
        self,
        node_name: str,
        node_id: str,
        psk: str | None = None,
        fanout: int = _DEFAULT_FANOUT,
        interval: float = _DEFAULT_GOSSIP_INTERVAL,
        send_fn: Callable[[str, dict[str, Any]], Any] | None = None,
    ):
        self.node_name = node_name
        self.node_id = node_id
        self.psk = psk or _settings.psk
        self.fanout = fanout
        self.interval = interval
        self.send_fn = send_fn

        # Table d'état du cluster : node_id -> NodeMetrics
        self._cluster_metrics: dict[str, NodeMetrics] = {}
        # Contacts connus : node_id -> endpoint (ex: "ws://192.168.1.10:8770")
        self._peers: dict[str, str] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._callbacks: list[Callable[[dict[str, NodeMetrics]], None]] = []

    def register_callback(self, cb: Callable[[dict[str, NodeMetrics]], None]) -> None:
        """Enregistre un écouteur appelé à chaque mise à jour du cluster."""
        self._callbacks.append(cb)

    def set_peer_endpoint(self, node_id: str, endpoint: str) -> None:
        """Ajoute ou met à jour l'adresse d'un pair pour le potinage Gossip."""
        if node_id != self.node_id:
            self._peers[node_id] = endpoint

    def remove_peer(self, node_id: str) -> None:
        self._peers.pop(node_id, None)
        self._cluster_metrics.pop(node_id, None)

    def update_local_metrics(
        self,
        cpu_percent: float = 0.0,
        memory_percent: float = 0.0,
        vram_free_mb: int = 0,
        active_tasks: int = 0,
        capacity: int = 10,
        skills: list[str] | None = None,
        endpoint: str | None = None,
        reputation_score: float = 1.0,
    ) -> NodeMetrics:
        """Met à jour les métriques locales du nœud courant."""
        metrics = NodeMetrics(
            node_name=self.node_name,
            node_id=self.node_id,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            vram_free_mb=vram_free_mb,
            active_tasks=active_tasks,
            capacity=capacity,
            skills=skills or [],
            timestamp=time.time(),
            endpoint=endpoint,
            reputation_score=reputation_score,
        )
        self._cluster_metrics[self.node_id] = metrics
        return metrics

    def get_cluster_metrics(self, include_stale: bool = False) -> dict[str, NodeMetrics]:
        """Retourne les métriques de l'ensemble des nœuds connus du maillage."""
        if include_stale:
            return dict(self._cluster_metrics)
        return {
            nid: m
            for nid, m in self._cluster_metrics.items()
            if not m.is_stale(_METRICS_TTL)
        }

    def get_best_node_for_task(self, required_skill: str | None = None) -> NodeMetrics | None:
        """Sélectionne le nœud le plus optimal (charge CPU/RAM minimale et VRAM disponible)."""
        active = [
            m for m in self.get_cluster_metrics().values()
            if not required_skill or required_skill in m.skills
        ]
        if not active:
            return self._cluster_metrics.get(self.node_id)

        # Tri : plus de VRAM, moins de charge CPU, moins de tâches actives, réputation maximale
        return min(
            active,
            key=lambda m: (
                m.active_tasks / max(1, m.capacity),
                m.cpu_percent,
                -m.vram_free_mb,
                -m.reputation_score,
            ),
        )

    def pack_gossip_message(self, max_entries: int = 10) -> dict[str, Any]:
        """Prépare un message Gossip contenant un échantillon des métriques les plus récentes."""
        active_entries = list(self.get_cluster_metrics(include_stale=False).values())
        active_entries.sort(key=lambda m: m.timestamp, reverse=True)
        selected = [m.to_dict() for m in active_entries[:max_entries]]

        payload: dict[str, Any] = {
            "type": "gossip_rumor",
            "sender_id": self.node_id,
            "sender_name": self.node_name,
            "metrics": selected,
            "ts": time.time(),
        }

        if self.psk:
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            payload[_GOSSIP_SIGNATURE_FIELD] = hmac.new(
                self.psk.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
            ).hexdigest()

        return payload

    def process_incoming_gossip(self, payload: dict[str, Any]) -> bool:
        """Traite un message Gossip reçu d'un pair et fusionne les métriques plus récentes."""
        if not isinstance(payload, dict) or payload.get("type") != "gossip_rumor":
            return False

        if self.psk:
            sig = payload.get(_GOSSIP_SIGNATURE_FIELD)
            unsigned = {k: v for k, v in payload.items() if k != _GOSSIP_SIGNATURE_FIELD}
            canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
            expected = hmac.new(
                self.psk.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            if not isinstance(sig, str) or not hmac.compare_digest(expected, sig):
                logger.warning("Message Gossip rejeté : signature HMAC invalide")
                return False

        metrics_list = payload.get("metrics", [])
        updated = False

        for raw_item in metrics_list:
            if not isinstance(raw_item, dict):
                continue
            try:
                candidate = NodeMetrics.from_dict(raw_item)
            except Exception:
                continue

            current = self._cluster_metrics.get(candidate.node_id)
            if current is None or candidate.timestamp > current.timestamp:
                self._cluster_metrics[candidate.node_id] = candidate
                if candidate.endpoint and candidate.node_id != self.node_id:
                    self._peers[candidate.node_id] = candidate.endpoint
                updated = True

        if updated:
            for cb in self._callbacks:
                try:
                    cb(dict(self._cluster_metrics))
                except Exception as exc:
                    logger.debug(f"Erreur callback Gossip: {exc}")

        return updated

    async def start(self) -> None:
        """Démarre la boucle asynchrone d'échange périodique Gossip."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._gossip_loop())
        logger.info(f"Protocole Gossip démarré pour le nœud '{self.node_name}' (fanout={self.fanout})")

    async def stop(self) -> None:
        """Arrête la boucle Gossip."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _gossip_loop(self) -> None:
        """Boucle de dissémination périodique vers un échantillon aléatoire de pairs."""
        while self._running:
            try:
                await asyncio.sleep(self.interval + random.uniform(-0.5, 0.5))
                if not self._peers or not self.send_fn:
                    continue

                available_peer_ids = list(self._peers.keys())
                target_count = min(self.fanout, len(available_peer_ids))
                selected_targets = random.sample(available_peer_ids, target_count)

                msg = self.pack_gossip_message()
                for target_id in selected_targets:
                    endpoint = self._peers.get(target_id)
                    if endpoint and self.send_fn is not None:
                        try:
                            res = self.send_fn(endpoint, msg)
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception as e:
                            logger.debug(f"Échec envoi Gossip vers {endpoint}: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Erreur dans la boucle Gossip: {e}")
