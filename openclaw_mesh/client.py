"""
Client P2P OpenClawMesh — Communication, découverte et délégation de tâches.

Permet à un agent OpenClaw :
- D'interroger n'importe quel nœud JarvisMesh / OpenClawMesh sur le LAN.
- De router automatiquement les tâches vers le nœud le plus adapté.
- De recevoir les réponses complètes ou les chunks en streaming token-par-token.
- De signer les requêtes avec HMAC-SHA256 ou Ed25519.
"""

from __future__ import annotations

import asyncio
import logging
import ssl as ssl_module
import time
import uuid
from collections.abc import Callable
from typing import Any

import websockets

from .config import get_settings
from .crypto import NodeIdentity
from .discovery import MeshDiscovery, PeerInfo
from .protocol import (
    DESCRIBE_SKILL,
    HEALTH_SKILL,
    TaskRequest,
    TaskResponse,
    parse_message,
)

logger = logging.getLogger("openclaw_mesh.client")
_settings = get_settings()


def _is_ws_closed(ws: Any) -> bool:
    if ws is None:
        return True
    if hasattr(ws, "closed"):
        return bool(ws.closed)
    if hasattr(ws, "state"):
        state_str = str(ws.state)
        state_name = getattr(ws.state, "name", "")
        return state_str in ("State.CLOSED", "State.CLOSING") or state_name in ("CLOSED", "CLOSING")
    return False


class MeshClient:
    """Client P2P asynchrone pour interagir avec le réseau JarvisMesh / OpenClawMesh."""

    def __init__(
        self,
        name: str | None = None,
        psk: str | None = None,
        identity: NodeIdentity | None = None,
        ssl_context: ssl_module.SSLContext | None = None,
        discovery: MeshDiscovery | None = None,
        enable_discovery: bool | None = None,
        dht: Any | None = None,
        relay_url: str | None = None,
    ):
        self.name = name or _settings.client_name
        self.psk = psk or _settings.psk
        self.identity = identity
        self.ssl_context = ssl_context
        self.dht = dht
        self.relay_url = relay_url
        self.quic_transport: Any | None = None
        self.gossipsub: Any | None = None

        # Une option explicitement fournie doit primer sur la configuration globale.
        discovery_enabled = (
            enable_discovery if enable_discovery is not None else _settings.mdns_enabled
        )
        self.discovery = discovery or (
            MeshDiscovery(node_name=self.name) if discovery_enabled else None
        )
        self.static_peers: dict[str, PeerInfo] = {}
        self.guichet_peers: dict[str, PeerInfo] = {}
        self.freebox_client: Any | None = None
        if _settings.freebox_guichet_enabled:
            from .network.freebox_guichet import FreeboxGuichetClient

            self.freebox_client = FreeboxGuichetClient(
                guichet_url=_settings.freebox_guichet_url,
                name=self.name,
            )

        # Pool de connexions WebSockets persistantes {endpoint_key: WebSocketClientProtocol}
        self._pool: dict[str, Any] = {}
        self._send_locks: dict[str, asyncio.Lock] = {}
        self._reader_tasks: dict[str, asyncio.Task] = {}
        self._pending: dict[str, dict[str, asyncio.Future]] = {}  # endpoint -> {req_id -> Future}
        self._stream_cbs: dict[
            str, dict[str, Callable[[Any], None]]
        ] = {}  # endpoint -> {req_id -> callback}

        # Cache d'introspection et de santé
        self._peer_skills_cache: dict[str, list[str]] = {}
        self._peer_health_cache: dict[str, dict] = {}
        self._rr_cursor: dict[str, int] = {}

    async def sync_guichet_peers(self) -> dict[str, PeerInfo]:
        """Interroge le Guichet Unique Freebox pour découvrir et mettre à jour tous les pairs actifs."""
        if not self.freebox_client:
            return {}
        try:
            data = await self.freebox_client.fetch_global_ip_directory()
            if not data or "directory" not in data:
                return {}

            for item in data.get("directory", []):
                pname = item.get("name")
                status = item.get("status", "offline")
                if not pname or status != "online":
                    continue
                if pname == self.name:
                    continue

                local_ip = item.get("local_ip")
                pub_ip = item.get("public_ip")
                port = item.get("port", 8770)
                skills = item.get("skills", [])

                # Déterminer la meilleure IP joignable
                if local_ip and not local_ip.startswith("127.") and not local_ip.startswith("fe80:"):
                    addr = local_ip
                else:
                    addr = pub_ip or local_ip or "127.0.0.1"

                peer = PeerInfo(
                    name=pname,
                    address=addr,
                    port=port,
                    skills=skills,
                    service_type="freebox_guichet",
                    last_seen=time.time(),
                )
                self.guichet_peers[pname] = peer
                nid = item.get("node_id")
                if nid:
                    self.guichet_peers[nid] = peer

            return self.guichet_peers
        except Exception as e:
            logger.debug(f"Synchronisation Guichet Freebox: {e}")
            return {}

    async def start(self, enable_quic: bool | None = None) -> None:
        """Démarre la découverte mDNS, la synchronisation Freebox Guichet et le transport UDP QUIC."""
        if self.discovery:
            await self.discovery.start(advertise=False)

        if _settings.freebox_guichet_enabled and self.freebox_client:
            try:
                await self.sync_guichet_peers()
            except Exception as e:
                logger.debug(f"Sync initial Guichet Freebox: {e}")

        use_quic = enable_quic if enable_quic is not None else _settings.quic_enabled
        if use_quic and self.quic_transport is None:
            try:
                from .network.quic_webrtc import QUICWebRTCTransport

                self.quic_transport = QUICWebRTCTransport(
                    node_name=self.name,
                    host="0.0.0.0",
                    port=0,  # Port UDP éphémère pour le client
                    psk=self.psk,
                    identity=self.identity,
                )
                await self.quic_transport.start()
            except Exception as e:
                logger.debug(f"Transport client QUIC UDP non démarré: {e}")

    async def stop(self) -> None:
        """Ferme toutes les connexions et arrête la découverte et les transports."""
        if self.quic_transport:
            await self.quic_transport.stop()
            self.quic_transport = None

        if self.gossipsub:
            await self.gossipsub.stop()
            self.gossipsub = None

        if self.discovery:
            await self.discovery.stop()

        for task in list(self._reader_tasks.values()):
            task.cancel()
        self._reader_tasks.clear()

        for ws in list(self._pool.values()):
            try:
                if not _is_ws_closed(ws):
                    await ws.close()
            except Exception:
                pass
        self._pool.clear()
        self._send_locks.clear()
        self._pending.clear()
        self._stream_cbs.clear()

    # ------------------------------------------------------------------ #
    # Gestion des Pairs & Découverte
    # ------------------------------------------------------------------ #
    def add_peer(
        self, name: str, address: str, port: int, skills: list[str] | None = None
    ) -> PeerInfo:
        """Enregistre manuellement un pair statique."""
        peer = PeerInfo(
            name=name, address=address, port=port, skills=skills or [], service_type="static"
        )
        self.static_peers[name] = peer
        return peer

    def list_peers(self) -> dict[str, PeerInfo]:
        """Retourne l'ensemble des pairs connus (mDNS + Guichet Freebox + statiques)."""
        peers = dict(self.static_peers)
        peers.update(self.guichet_peers)
        if self.discovery:
            peers.update(self.discovery.list_peers())
        return peers

    async def discover_skills(self, peer_target: str, timeout: float = 4.0) -> dict[str, Any]:
        """Introspecte le catalogue complet d'un pair via _describe_skills."""
        resp = await self.call(peer_target, DESCRIBE_SKILL, {}, timeout=timeout)
        if resp.ok and isinstance(resp.result, dict):
            skills = resp.result.get("skills", [])
            if isinstance(skills, list):
                self._peer_skills_cache[peer_target] = skills
            return resp.result
        return {"skills": [], "error": resp.error}

    async def check_health(self, peer_target: str, timeout: float = 3.0) -> dict[str, Any]:
        """Sonde la santé et la charge d'un pair via _health."""
        t0 = time.perf_counter()
        resp = await self.call(peer_target, HEALTH_SKILL, {}, timeout=timeout)
        rtt = (time.perf_counter() - t0) * 1000.0
        if resp.ok and isinstance(resp.result, dict):
            data = resp.result
            data["rtt_ms"] = round(rtt, 2)
            self._peer_health_cache[peer_target] = data
            return data
        return {"status": "error", "error": resp.error, "rtt_ms": round(rtt, 2)}

    def find_best_peer_for_skill(self, skill: str) -> str | None:
        """Sélectionne le meilleur pair pour une compétence donnée (par charge/latence ou round-robin)."""
        candidates: list[str] = []
        all_peers = self.list_peers()

        for pname, pinfo in all_peers.items():
            skills = self._peer_skills_cache.get(pname, pinfo.skills)
            if skill in skills:
                candidates.append(pname)

        if not candidates:
            return None

        # Tri par charge active si santé connue
        scored = []
        for c in candidates:
            health = self._peer_health_cache.get(c)
            if health and "active_tasks" in health:
                scored.append((health.get("active_tasks", 0), health.get("rtt_ms", 999.0), c))
            else:
                scored.append((10, 999.0, c))

        scored.sort(key=lambda x: (x[0], x[1]))
        return scored[0][2]

    # ------------------------------------------------------------------ #
    # Connexion & Transport WebSocket
    # ------------------------------------------------------------------ #
    async def _resolve_endpoint(self, target: str) -> tuple[str, str]:
        """Résout un nom de pair ou une URL directe en (endpoint_key, ws_url)."""
        if target.startswith("ws://") or target.startswith("wss://"):
            return target, target

        all_peers = self.list_peers()
        if target in all_peers:
            peer = all_peers[target]
            return target, peer.ws_url

        # Tenter une synchronisation avec le Guichet Unique Freebox si non trouvé localement
        if self.freebox_client:
            await self.sync_guichet_peers()
            all_peers = self.list_peers()
            if target in all_peers:
                peer = all_peers[target]
                return target, peer.ws_url

        # Format host:port direct
        if ":" in target and not target.startswith("http"):
            parts = target.split(":")
            return target, f"ws://{parts[0]}:{parts[1]}"

        # Si un relais WAN est configuré, l'utiliser comme fallback
        if self.relay_url:
            return target, self.relay_url

        raise ValueError(
            f"Pair ou endpoint inconnu : '{target}'. Pairs disponibles : {list(all_peers.keys())}"
        )

    async def _get_connection(self, endpoint_key: str, ws_url: str) -> Any:
        """Obtient ou réutilise une connexion WebSocket persistante multiplexée."""
        ws = self._pool.get(endpoint_key)
        if _is_ws_closed(ws):
            try:
                ws = await websockets.connect(
                    ws_url,
                    ssl=self.ssl_context,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=16 * 1024 * 1024,  # 16 MB max payload
                )
            except Exception as e:
                raise ConnectionError(
                    f"Impossible de se connecter à {ws_url} ({endpoint_key}) : {e}"
                ) from e

            self._pool[endpoint_key] = ws
            self._send_locks[endpoint_key] = asyncio.Lock()
            self._pending[endpoint_key] = {}
            self._stream_cbs[endpoint_key] = {}
            self._reader_tasks[endpoint_key] = asyncio.create_task(
                self._reader_loop(endpoint_key, ws)
            )

        return ws

    async def _reader_loop(self, endpoint_key: str, ws: Any) -> None:
        """Boucle de lecture unique multiplexant les réponses et chunks entrants."""
        try:
            async for raw in ws:
                try:
                    data = parse_message(raw)
                except Exception as parse_err:
                    logger.warning(f"Message JSON invalide reçu de {endpoint_key}: {parse_err}")
                    continue

                msg_type = data.get("type")
                req_id = data.get("request_id")

                if not req_id:
                    continue

                # 1. Chunk intermédiaire
                if msg_type == "task_chunk":
                    cb = self._stream_cbs.get(endpoint_key, {}).get(req_id)
                    if cb:
                        chunk_val = data.get("chunk")
                        try:
                            if asyncio.iscoroutinefunction(cb):
                                asyncio.ensure_future(cb(chunk_val))
                            else:
                                cb(chunk_val)
                        except Exception as cb_err:
                            logger.error(f"Erreur callback streaming: {cb_err}")

                # 2. Réponse finale
                elif msg_type == "task_response":
                    pending = self._pending.get(endpoint_key, {})
                    fut = pending.pop(req_id, None)
                    self._stream_cbs.get(endpoint_key, {}).pop(req_id, None)

                    if fut and not fut.done():
                        resp = TaskResponse.from_dict(data)
                        fut.set_result(resp)

        except (asyncio.CancelledError, websockets.ConnectionClosed):
            pass
        except Exception as e:
            logger.debug(f"Déconnexion du pair {endpoint_key}: {e}")
        finally:
            self._pool.pop(endpoint_key, None)
            self._send_locks.pop(endpoint_key, None)
            self._stream_cbs.pop(endpoint_key, None)
            pending = self._pending.pop(endpoint_key, {})
            for fut in pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionResetError(f"Connexion perdue avec {endpoint_key}"))

    # ------------------------------------------------------------------ #
    # Appels de Compétences (Call, Stream, Delegate)
    # ------------------------------------------------------------------ #
    async def call(
        self,
        target: str,
        skill: str,
        payload: dict | None = None,
        timeout: float = 60.0,
    ) -> TaskResponse:
        """
        Envoie une requête d'exécution synchrone à un pair.
        target : Nom du pair (ex: 'mac-m3') ou URL ('ws://192.168.1.50:8765').
        """
        endpoint_key, ws_url = await self._resolve_endpoint(target)
        ws = await self._get_connection(endpoint_key, ws_url)

        req = TaskRequest(
            skill=skill,
            payload=payload or {},
            origin=self.name,
        )

        # Signature HMAC ou Ed25519
        if self.identity:
            req.sign_ed25519(self.identity)
        elif self.psk:
            req.sign(self.psk)

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[TaskResponse] = loop.create_future()
        self._pending[endpoint_key][req.request_id] = fut

        lock = self._send_locks[endpoint_key]
        try:
            async with lock:
                await ws.send(req.to_json())
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.get(endpoint_key, {}).pop(req.request_id, None)
            return TaskResponse(
                request_id=req.request_id,
                ok=False,
                error=f"Timeout ({timeout}s) dépassé lors de l'appel de '{skill}' sur {target}",
                handled_by=target,
            )
        except Exception as e:
            self._pending.get(endpoint_key, {}).pop(req.request_id, None)
            return TaskResponse(
                request_id=req.request_id,
                ok=False,
                error=f"Erreur d'appel: {e}",
                handled_by=target,
            )

    async def call_stream(
        self,
        target: str,
        skill: str,
        payload: dict | None = None,
        on_chunk: Callable[[Any], None] | None = None,
        timeout: float = 120.0,
    ) -> TaskResponse:
        """
        Envoie une requête et consomme les chunks intermédiaires au fil de l'eau.
        """
        endpoint_key, ws_url = await self._resolve_endpoint(target)
        ws = await self._get_connection(endpoint_key, ws_url)

        req = TaskRequest(
            skill=skill,
            payload=payload or {},
            origin=self.name,
        )

        if self.identity:
            req.sign_ed25519(self.identity)
        elif self.psk:
            req.sign(self.psk)

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[TaskResponse] = loop.create_future()
        self._pending[endpoint_key][req.request_id] = fut

        if on_chunk:
            self._stream_cbs[endpoint_key][req.request_id] = on_chunk

        lock = self._send_locks[endpoint_key]
        try:
            async with lock:
                await ws.send(req.to_json())
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.get(endpoint_key, {}).pop(req.request_id, None)
            self._stream_cbs.get(endpoint_key, {}).pop(req.request_id, None)
            return TaskResponse(
                request_id=req.request_id,
                ok=False,
                error=f"Timeout streaming ({timeout}s) dépassé sur '{skill}'",
                handled_by=target,
            )
        except Exception as e:
            self._pending.get(endpoint_key, {}).pop(req.request_id, None)
            self._stream_cbs.get(endpoint_key, {}).pop(req.request_id, None)
            return TaskResponse(
                request_id=req.request_id,
                ok=False,
                error=f"Erreur d'appel streaming: {e}",
                handled_by=target,
            )

    async def call_stream_quic(
        self,
        target: str | tuple[str, int],
        skill: str,
        payload: dict | None = None,
        on_chunk: Callable[[Any], None] | None = None,
        timeout: float = 60.0,
    ) -> TaskResponse:
        """
        Envoie une requête via tunnel direct UDP QUIC/WebRTC et consomme les tokens avec latence sub-10ms.
        """
        if self.quic_transport is None:
            await self.start(enable_quic=True)
            if self.quic_transport is None:
                raise RuntimeError("Transport QUIC/WebRTC UDP indisponible")

        # Résolution de l'adresse UDP (host, port)
        if isinstance(target, tuple):
            peer_addr = target
            peer_label = f"{peer_addr[0]}:{peer_addr[1]}"
        else:
            all_peers = self.list_peers()
            if target in all_peers:
                peer = all_peers[target]
                q_port = getattr(peer, "quic_port", None) or (
                    peer.port + 5 if peer.port != 8770 else _settings.quic_port
                )
                peer_addr = (peer.address, q_port)
                peer_label = target
            elif ":" in target and not target.startswith("ws"):
                parts = target.split(":")
                peer_addr = (parts[0], int(parts[1]))
                peer_label = target
            else:
                raise ValueError(f"Impossible de résoudre l'adresse UDP pour '{target}'")

        req = TaskRequest(
            skill=skill,
            payload=payload or {},
            origin=self.name,
        )
        if self.identity:
            req.sign_ed25519(self.identity)
        elif self.psk:
            req.sign(self.psk)

        stream = await self.quic_transport.open_stream(peer_addr, req)
        final_response: TaskResponse | None = None

        async def _read_stream():
            nonlocal final_response
            async for raw_chunk in stream.read_chunks():
                try:
                    data = parse_message(raw_chunk.decode("utf-8"))
                    msg_type = data.get("type")
                    if msg_type == "task_chunk":
                        chunk_val = data.get("chunk")
                        if on_chunk:
                            if asyncio.iscoroutinefunction(on_chunk):
                                await on_chunk(chunk_val)
                            else:
                                on_chunk(chunk_val)
                    elif msg_type == "task_response":
                        final_response = TaskResponse.from_dict(data)
                except Exception as e:
                    logger.debug(f"Erreur parsing chunk QUIC: {e}")

        try:
            await asyncio.wait_for(_read_stream(), timeout=timeout)
            if final_response:
                return final_response
            return TaskResponse(
                request_id=req.request_id,
                ok=True,
                result={
                    "streamed_chunks": stream.token_count,
                    "first_token_latency_ms": stream.first_token_latency_ms,
                },
                handled_by=peer_label,
                streamed=True,
            )
        except asyncio.TimeoutError:
            return TaskResponse(
                request_id=req.request_id,
                ok=False,
                error=f"Timeout QUIC streaming ({timeout}s) dépassé sur '{skill}'",
                handled_by=peer_label,
            )
        except Exception as e:
            return TaskResponse(
                request_id=req.request_id,
                ok=False,
                error=f"Erreur streaming QUIC: {e}",
                handled_by=peer_label,
            )

    async def delegate(
        self,
        skill: str,
        payload: dict | None = None,
        on_chunk: Callable[[Any], None] | None = None,
        prefer_quic: bool = False,
        timeout: float = 60.0,
    ) -> TaskResponse:
        """
        Routage intelligent : trouve automatiquement le meilleur pair fournissant `skill`
        (via découverte locale mDNS, Guichet Unique Freebox ou Provider Records DHT)
        et lui délègue l'exécution.
        """
        best_peer = self.find_best_peer_for_skill(skill)

        # Fallback 1 : Si non trouvé, synchroniser avec le Guichet Unique Freebox
        if not best_peer and self.freebox_client:
            try:
                await self.sync_guichet_peers()
                best_peer = self.find_best_peer_for_skill(skill)
            except Exception as ex_g:
                logger.debug(f"Recherche compétence Guichet Freebox: {ex_g}")

        # Fallback 2 : Si non trouvé et DHT active, chercher via Provider Records DHT Kademlia
        if not best_peer and self.dht:
            try:
                providers = await self.dht.find_providers_distributed(f"skill:{skill}", timeout=2.0)
                if providers:
                    p = providers[0]
                    pname = p.get("name", "dht-peer")
                    phost = p.get("host", "127.0.0.1")
                    pport = int(p.get("port", 8770))
                    self.add_peer(pname, phost, pport, skills=[skill])
                    best_peer = pname
            except Exception as dht_err:
                logger.debug(f"Recherche providers DHT échouée: {dht_err}")

        if not best_peer:
            return TaskResponse(
                request_id=uuid.uuid4().hex[:8],
                ok=False,
                error=f"Aucun pair sur le réseau ne fournit la compétence requise : '{skill}'",
            )

        # Tentative QUIC ultra-basse latence si demandée ou streaming token
        if prefer_quic and on_chunk:
            try:
                return await self.call_stream_quic(
                    best_peer, skill, payload, on_chunk=on_chunk, timeout=timeout
                )
            except Exception as quic_err:
                logger.debug(f"Fallback WebSocket suite à échec QUIC: {quic_err}")

        if on_chunk:
            return await self.call_stream(
                best_peer, skill, payload, on_chunk=on_chunk, timeout=timeout
            )
        return await self.call(best_peer, skill, payload, timeout=timeout)
