"""
Serveur de Nœud P2P OpenClawMesh (OpenClawMeshNode).

Permet à un agent OpenClaw de démarrer un serveur local de compétences,
de s'annoncer sur le réseau mDNS et de servir des requêtes entrantes
provenant d'autres nœuds OpenClaw ou JarvisMesh.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import ssl as ssl_module
import time
from collections.abc import Callable
from typing import Any

import websockets

from .bridge import SkillRegistry
from .config import get_settings
from .crypto import NodeIdentity, TrustStore, verify_ed25519_signature
from .discovery import MeshDiscovery, get_local_ip
from .protocol import (
    DESCRIBE_SKILL,
    HEALTH_SKILL,
    TaskChunk,
    TaskRequest,
    TaskResponse,
    parse_message,
)

logger = logging.getLogger("openclaw_mesh.node")
_settings = get_settings()


def _bounded_message(message: str) -> str:
    """Refuse les sorties distantes dépassant la limite de configuration."""
    if len(message.encode("utf-8")) > _settings.max_output_bytes:
        raise ValueError("Sortie de compétence trop volumineuse")
    return message


class OpenClawMeshNode:
    """Nœud P2P serveur pour OpenClaw, 100% interopérable avec JarvisMesh."""

    def __init__(
        self,
        name: str | None = None,
        port: int | None = None,
        host: str | None = None,
        advertise_ip: str | None = None,
        registry: SkillRegistry | None = None,
        psk: str | None = None,
        identity: NodeIdentity | None = None,
        trust_store: TrustStore | None = None,
        ssl_context: ssl_module.SSLContext | None = None,
        health_extra: Callable[[], dict] | None = None,
        guichet_url: str | None = None,
    ):
        self.name = name or _settings.node_name
        self.port = port or _settings.default_port
        self.host = host or _settings.default_host
        self.advertise_ip = advertise_ip or get_local_ip()
        self.registry = registry or SkillRegistry(name=self.name)
        self.psk = psk or _settings.psk
        self.identity = identity
        self.trust_store = trust_store
        self.ssl_context = ssl_context
        self.health_extra = health_extra
        self.guichet_url = guichet_url

        self.discovery: MeshDiscovery | None = None
        self.dht: Any | None = None
        self._dht_task: asyncio.Task | None = None
        self._nat_profile: Any | None = None
        self.quic_transport: Any | None = None
        self.gossipsub: Any | None = None
        self.freebox_client: Any | None = None
        self._ws_server = None
        self._active_tasks = 0
        self._task_semaphore = asyncio.Semaphore(max(1, _settings.max_active_tasks))
        self._queue_semaphore = asyncio.Semaphore(
            max(1, _settings.max_active_tasks + _settings.max_queued_tasks)
        )
        self._start_time = time.time()
        self._running = False

    @staticmethod
    def _try_acquire(sem: asyncio.Semaphore) -> bool:
        """Acquisition non-bloquante et atomique d'un asyncio.Semaphore.

        Evite le TOCTOU du pattern locked()+acquire() séparés en lisant
        et décrémentant directement le compteur interne dans un seul appel
        synchrone (opération atomique dans la boucle d'événements asyncio
        car Python n'est pas réentrant au niveau d'une instruction).
        """
        if sem._value > 0:  # noqa: SLF001
            sem._value -= 1  # noqa: SLF001
            return True
        return False

    async def start(
        self,
        enable_zeroconf: bool = True,
        enable_wan: bool | None = None,
        enable_dht: bool | None = None,
        enable_quic: bool | None = None,
        enable_gossipsub: bool | None = None,
        dht_port: int = 8780,
        quic_port: int | None = None,
        relay_url: str | None = None,
    ) -> None:
        """Démarre le serveur WebSocket, QUIC/WebRTC UDP, Zeroconf, DHT Kademlia et GossipSub."""
        if self._running:
            return
        if self.host not in {"0.0.0.0", "127.0.0.1", "::1", "localhost", "::"}:
            if not self.ssl_context:
                try:
                    from .crypto import create_ephemeral_ssl_context

                    self.ssl_context = create_ephemeral_ssl_context()
                    logger.info("Certificat TLS éphémère auto-généré pour le nœud WAN.")
                except Exception as exc:
                    raise RuntimeError(f"Un nœud exposé doit utiliser TLS : {exc}") from exc
            if not (self.psk or self.trust_store or self.identity):
                import secrets

                self.psk = secrets.token_urlsafe(32)
                logger.warning(f"Clé PSK de sécurité auto-générée pour le nœud WAN: {self.psk}")

        self._start_time = time.time()

        # 0. RACCORDEMENT PRIORITAIRE AU GUICHET UNIQUE FREEBOX ULTRA (PREMIER DÉMARRAGE & ANCRE)
        initial_reg_res = None
        if _settings.freebox_guichet_enabled:
            try:
                from .network.freebox_guichet import FreeboxGuichetClient

                nid = getattr(self.identity, "node_id", None) or f"node-{self.name.lower().replace(' ', '-')}-{self.port}"
                target_guichet_url = self.guichet_url or _settings.freebox_guichet_url
                self.freebox_client = FreeboxGuichetClient(
                    guichet_url=target_guichet_url,
                    node_id=nid,
                    name=self.name,
                    port=self.port,
                    dht_port=dht_port,
                    skills=self.registry.list_remote_names(),
                    pubkey=getattr(self.identity, "public_key_hex", None) if self.identity else None,
                )
                logger.info("⚡ [Étape 1 Prioritaire] Raccordement au Guichet Unique Freebox...")
                initial_reg_res = await self.freebox_client.auto_onboard_first_start()
            except Exception as e:
                logger.debug(f"Auto-raccordement initial Freebox Guichet: {e}")

        self._ws_server = await websockets.serve(
            self._handle_ws,
            self.host,
            self.port,
            ssl=self.ssl_context,
            max_size=16 * 1024 * 1024,
        )
        self._running = True

        # 1. Transport Ultra-Basse Latence QUIC / WebRTC DataChannels (UDP)
        use_quic = enable_quic if enable_quic is not None else _settings.quic_enabled
        q_port = quic_port or (self.port + 5 if self.port != 8770 else _settings.quic_port)
        if use_quic:
            try:
                from .network.quic_webrtc import QUICWebRTCTransport

                self.quic_transport = QUICWebRTCTransport(
                    node_name=self.name,
                    host=self.host,
                    port=q_port,
                    psk=self.psk,
                    identity=self.identity,
                )
                self.quic_transport.set_request_handler(self._handle_quic_request)
                await self.quic_transport.start()
            except Exception as e:
                logger.warning(f"Avertissement démarrage transport QUIC/WebRTC: {e}")

        # 2. Découverte locale mDNS Zeroconf
        if enable_zeroconf:
            skills_list = self.registry.list_remote_names()
            self.discovery = MeshDiscovery(
                node_name=self.name,
                port=self.port,
                skills=skills_list,
                advertise_ip=self.advertise_ip,
            )
            await self.discovery.start(advertise=True)

        # 3. Découverte & Ouverture WAN Universelle (UPnP IGD, PCP, DHT Kademlia)
        use_wan = enable_wan if enable_wan is not None else _settings.wan_enabled
        use_dht = enable_dht if enable_dht is not None else _settings.dht_enabled

        if use_wan or use_dht:
            try:
                from .network.nat_traversal import discover_nat_and_public_ip

                self._nat_profile = await discover_nat_and_public_ip(
                    local_port=self.port,
                    enabled=True,
                    try_upnp=_settings.upnp_enabled,
                    extra_udp_ports=[q_port, dht_port],
                )
                public_host = self._nat_profile.public_ip or self.advertise_ip
            except Exception as e:
                logger.debug(f"Découverte & ouverture NAT WAN: {e}")
                public_host = self.advertise_ip

            try:
                from .network.dht import KademliaDHT

                self.dht = KademliaDHT(
                    host="0.0.0.0",
                    port=dht_port,
                    name=self.name,
                    psk=self.psk,
                )
                await self.dht.start_network()
                await self.dht.bootstrap_global()
                self._dht_task = self.dht.start_auto_refresh(interval_seconds=45.0)

                # Amorçage direct via les pairs reçus du Guichet Freebox
                if initial_reg_res and "bootstrap_peers" in initial_reg_res:
                    for peer in initial_reg_res.get("bootstrap_peers", []):
                        p_host = peer.get("public_ip") or peer.get("local_ip")
                        p_dht_port = peer.get("dht_port", 8780)
                        if p_host and p_dht_port:
                            asyncio.create_task(self.dht.ping_node(p_host, p_dht_port))

                # Publier nos compétences sur la toile mondiale DHT (Provider Records)
                for skill_name in self.registry.list_remote_names():
                    await self.dht.advertise_skill_distributed(
                        skill_name,
                        {
                            "name": self.name,
                            "host": public_host,
                            "port": self.port,
                            "quic_port": self.quic_transport.bound_port
                            if self.quic_transport
                            else None,
                            "skills": self.registry.list_remote_names(),
                        },
                    )
                logger.info(
                    f"✓ Nœud '{self.name}' raccordé au WAN et à la DHT Kademlia mondiale (UDP:{dht_port})"
                )
            except Exception as e:
                logger.warning(f"Avertissement DHT Kademlia WAN: {e}")

        # 4. Overlay Pub/Sub GossipSub v1.1
        use_gossipsub = (
            enable_gossipsub if enable_gossipsub is not None else _settings.gossipsub_enabled
        )
        if use_gossipsub:
            try:
                import hashlib

                from .network.gossipsub import GossipSubNode

                self.gossipsub = GossipSubNode(
                    node_id=hashlib.sha256(self.name.encode("utf-8")).hexdigest()[:16],
                    node_name=self.name,
                    psk=self.psk,
                )
                await self.gossipsub.start()
            except Exception as e:
                logger.warning(f"Avertissement démarrage GossipSub: {e}")

        logger.info(f"Nœud OpenClawMesh '{self.name}' démarré sur {self.host}:{self.port}")

    async def stop(self) -> None:
        """Arrête le serveur et l'ensemble des transports réseau."""
        if not self._running:
            return
        self._running = False

        if self.freebox_client:
            self.freebox_client.stop_heartbeat()
            self.freebox_client = None

        if self.gossipsub:
            await self.gossipsub.stop()
            self.gossipsub = None

        if self.quic_transport:
            await self.quic_transport.stop()
            self.quic_transport = None

        if self._dht_task:
            self._dht_task.cancel()
            self._dht_task = None

        if self.dht:
            await self.dht.stop_network()
            self.dht = None

        if self.discovery:
            await self.discovery.stop()
            self.discovery = None

        if self._ws_server:
            try:
                self._ws_server.close()
                if hasattr(self._ws_server, "wait_closed"):
                    res_wait = self._ws_server.wait_closed()
                    if inspect.isawaitable(res_wait):
                        await res_wait
            except Exception as e:
                logger.debug(f"Fermeture du serveur WebSocket: {e}")
            finally:
                self._ws_server = None

        logger.info(f"Nœud OpenClawMesh '{self.name}' arrêté.")

    # ------------------------------------------------------------------ #
    # Traitement des Requêtes Entrantes WebSocket
    # ------------------------------------------------------------------ #
    async def _handle_ws(self, ws: Any) -> None:
        """Traite une connexion entrante d'un pair."""
        send_lock = asyncio.Lock()
        try:
            async for raw in ws:
                # Acquisition atomique sans TOCTOU via _try_acquire.
                if self._try_acquire(self._queue_semaphore):
                    asyncio.create_task(self._process_message_with_timeout(ws, raw, send_lock))
                else:
                    # File pleine — rejeter cette requête sans fermer la connexion.
                    try:
                        import json as _json
                        data = _json.loads(raw)
                        req_id = data.get("request_id", "unknown")
                    except Exception:
                        req_id = "unknown"
                    from .protocol import TaskResponse as _TR
                    err = _TR(
                        request_id=req_id,
                        ok=False,
                        error="Capacité du nœud atteinte — réessayez plus tard",
                        handled_by=self.name,
                    )
                    async with send_lock:
                        await ws.send(err.to_json())
        except (asyncio.CancelledError, websockets.ConnectionClosed):
            pass
        except Exception as e:
            logger.debug(f"Connexion client fermée: {e}")

    async def _process_message_with_timeout(
        self,
        ws: Any,
        raw: str,
        send_lock: asyncio.Lock,
    ) -> None:
        try:
            await asyncio.wait_for(
                self._process_message(ws, raw, send_lock),
                timeout=max(0.1, _settings.task_timeout),
            )
        except asyncio.TimeoutError:
            logger.warning("Tâche P2P interrompue après dépassement du délai")
        finally:
            self._queue_semaphore.release()

    async def _process_message(
        self,
        ws: Any,
        raw: str,
        send_lock: asyncio.Lock,
    ) -> None:
        """Parse et exécute une TaskRequest."""
        try:
            data = parse_message(raw)
        except Exception as e:
            err_resp = TaskResponse(
                request_id="unknown",
                ok=False,
                error=f"JSON invalide: {e}",
                handled_by=self.name,
            )
            async with send_lock:
                await ws.send(err_resp.to_json())
            return

        msg_type = data.get("type", "task_request")
        if msg_type != "task_request":
            return

        try:
            req = TaskRequest.from_dict(data)
        except (TypeError, ValueError) as exc:
            err_resp = TaskResponse(
                request_id=str(data.get("request_id", "unknown")),
                ok=False,
                error=f"Requête invalide: {exc}",
                handled_by=self.name,
            )
            async with send_lock:
                await ws.send(err_resp.to_json())
            return

        # 1. Vérification d'Authentification HMAC-SHA256
        if self.psk:
            if not req.verify(self.psk):
                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=False,
                    error="Authentification échouée : signature HMAC-SHA256 invalide ou manquante",
                    handled_by=self.name,
                )
                async with send_lock:
                    await ws.send(resp.to_json())
                return

        # 2. Vérification d'Authentification Ed25519
        if self.trust_store:
            if not req.pubkey or not req.sig:
                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=False,
                    error="Authentification échouée : clé publique ou signature Ed25519 requise",
                    handled_by=self.name,
                )
                async with send_lock:
                    await ws.send(resp.to_json())
                return

            if not self.trust_store.is_trusted(req.pubkey):
                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=False,
                    error=f"Accès refusé : la clé publique '{req.pubkey}' n'est pas autorisée dans le TrustStore",
                    handled_by=self.name,
                )
                async with send_lock:
                    await ws.send(resp.to_json())
                return

            if not verify_ed25519_signature(
                public_key_hex=req.pubkey,
                request_id=req.request_id,
                origin=req.origin,
                skill=req.skill,
                ts=req.ts,
                payload=req.payload,
                signature_hex=req.sig,
            ):
                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=False,
                    error="Signature cryptographique Ed25519 invalide ou horodatage expiré",
                    handled_by=self.name,
                )
                async with send_lock:
                    await ws.send(resp.to_json())
                return

        # 3. Traitement des Compétences Réservées (_describe_skills, _health)
        if req.skill == DESCRIBE_SKILL:
            desc = self.registry.describe()
            resp = TaskResponse(
                request_id=req.request_id,
                ok=True,
                result=desc,
                handled_by=self.name,
            )
            async with send_lock:
                await ws.send(resp.to_json())
            return

        if req.skill == HEALTH_SKILL:
            health_data = {
                "status": "ok",
                "active_tasks": self._active_tasks,
                "uptime_seconds": round(time.time() - self._start_time, 2),
                "skills_count": len(self.registry.list_names()),
                "node_name": self.name,
                "client": "openclaw",
            }
            if self.health_extra:
                try:
                    extra = self.health_extra()
                    if isinstance(extra, dict):
                        health_data.update(extra)
                except Exception as extra_err:
                    logger.warning(f"Erreur health_extra: {extra_err}")

            resp = TaskResponse(
                request_id=req.request_id,
                ok=True,
                result=health_data,
                handled_by=self.name,
            )
            async with send_lock:
                await ws.send(resp.to_json())
            return

        # 4. Exécution de la Compétence Demandée
        handler = self.registry.get(req.skill)
        if handler is not None and not self.registry.is_remote_exposed(req.skill):
            resp = TaskResponse(
                request_id=req.request_id,
                ok=False,
                error="Compétence non exposée à distance",
                handled_by=self.name,
            )
            async with send_lock:
                await ws.send(resp.to_json())
            return
        if handler is None:
            resp = TaskResponse(
                request_id=req.request_id,
                ok=False,
                error=f"Compétence inconnue sur ce nœud : '{req.skill}'",
                handled_by=self.name,
            )
            async with send_lock:
                await ws.send(resp.to_json())
            return

        # Acquisition atomique sans TOCTOU via _try_acquire.
        if not self._try_acquire(self._task_semaphore):
            resp = TaskResponse(
                request_id=req.request_id,
                ok=False,
                error="Capacité du nœud atteinte",
                handled_by=self.name,
            )
            async with send_lock:
                await ws.send(resp.to_json())
            return
        self._active_tasks += 1
        output_bytes = 0
        try:
            # Gestion des générateurs asynchrones (Streaming)
            if inspect.isasyncgenfunction(handler):
                index = 0
                async for chunk in handler(req.payload):
                    chunk_msg = TaskChunk(request_id=req.request_id, index=index, chunk=chunk)
                    chunk_json = _bounded_message(chunk_msg.to_json())
                    output_bytes += len(chunk_json.encode("utf-8"))
                    if output_bytes > _settings.max_output_bytes:
                        raise ValueError("Flux de sortie trop volumineux")
                    async with send_lock:
                        await ws.send(chunk_json)
                    index += 1

                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=True,
                    result={"streamed_chunks": index},
                    handled_by=self.name,
                    streamed=True,
                )
                async with send_lock:
                    await ws.send(_bounded_message(resp.to_json()))

            # Gestion des générateurs synchrones (Streaming)
            elif inspect.isgeneratorfunction(handler):
                index = 0
                for chunk in handler(req.payload):
                    chunk_msg = TaskChunk(request_id=req.request_id, index=index, chunk=chunk)
                    chunk_json = _bounded_message(chunk_msg.to_json())
                    output_bytes += len(chunk_json.encode("utf-8"))
                    if output_bytes > _settings.max_output_bytes:
                        raise ValueError("Flux de sortie trop volumineux")
                    async with send_lock:
                        await ws.send(chunk_json)
                    index += 1

                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=True,
                    result={"streamed_chunks": index},
                    handled_by=self.name,
                    streamed=True,
                )
                async with send_lock:
                    await ws.send(_bounded_message(resp.to_json()))

            # Gestion des fonctions asynchrones
            elif inspect.iscoroutinefunction(handler):
                result = await handler(req.payload)
                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=True,
                    result=result,
                    handled_by=self.name,
                )
                async with send_lock:
                    await ws.send(_bounded_message(resp.to_json()))

            # Gestion des fonctions synchrones standard
            else:
                result = await asyncio.to_thread(handler, req.payload)
                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=True,
                    result=result,
                    handled_by=self.name,
                )
                async with send_lock:
                    await ws.send(_bounded_message(resp.to_json()))

        except Exception as exec_err:
            logger.error(f"Erreur lors de l'exécution de '{req.skill}': {exec_err}", exc_info=True)
            resp = TaskResponse(
                request_id=req.request_id,
                ok=False,
                error="Erreur d'exécution",
                handled_by=self.name,
            )
            async with send_lock:
                await ws.send(resp.to_json())
        finally:
            self._active_tasks = max(0, self._active_tasks - 1)
            self._task_semaphore.release()

    # ------------------------------------------------------------------ #
    # Traitement des Requêtes Entrantes QUIC / WebRTC Ultra-Basse Latence
    # ------------------------------------------------------------------ #
    async def _handle_quic_request(self, req: TaskRequest, stream: Any) -> None:
        """Traite une TaskRequest arrivant via flux QUIC/WebRTC UDP pour streaming token sub-10ms."""
        peer_addr = stream.session.peer_addr
        stream_id = stream.stream_id

        # 1. Vérification d'Authentification HMAC-SHA256
        if self.psk:
            if not req.verify(self.psk):
                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=False,
                    error="Authentification échouée : signature HMAC-SHA256 invalide",
                    handled_by=self.name,
                )
                if self.quic_transport:
                    await self.quic_transport.send_stream_data(
                        peer_addr, stream_id, resp.to_json().encode("utf-8")
                    )
                    await self.quic_transport.send_stream_fin(peer_addr, stream_id)
                return

        # 2. Compétences Réservées
        if req.skill == DESCRIBE_SKILL:
            desc = self.registry.describe()
            resp = TaskResponse(
                request_id=req.request_id, ok=True, result=desc, handled_by=self.name
            )
            if self.quic_transport:
                await self.quic_transport.send_stream_data(
                    peer_addr, stream_id, resp.to_json().encode("utf-8")
                )
                await self.quic_transport.send_stream_fin(peer_addr, stream_id)
            return

        if req.skill == HEALTH_SKILL:
            health_data = {
                "status": "ok",
                "active_tasks": self._active_tasks,
                "uptime_seconds": round(time.time() - self._start_time, 2),
                "skills_count": len(self.registry.list_names()),
                "node_name": self.name,
                "transport": "quic_webrtc_udp",
            }
            resp = TaskResponse(
                request_id=req.request_id, ok=True, result=health_data, handled_by=self.name
            )
            if self.quic_transport:
                await self.quic_transport.send_stream_data(
                    peer_addr, stream_id, resp.to_json().encode("utf-8")
                )
                await self.quic_transport.send_stream_fin(peer_addr, stream_id)
            return

        # 3. Exécution de la compétence
        handler = self.registry.get(req.skill)
        if handler is None:
            resp = TaskResponse(
                request_id=req.request_id,
                ok=False,
                error=f"Compétence inconnue sur ce nœud : '{req.skill}'",
                handled_by=self.name,
            )
            if self.quic_transport:
                await self.quic_transport.send_stream_data(
                    peer_addr, stream_id, resp.to_json().encode("utf-8")
                )
                await self.quic_transport.send_stream_fin(peer_addr, stream_id)
            return

        await self._task_semaphore.acquire()
        self._active_tasks += 1
        try:
            if inspect.isasyncgenfunction(handler):
                idx = 0
                async for chunk in handler(req.payload):
                    chunk_msg = TaskChunk(request_id=req.request_id, index=idx, chunk=chunk)
                    if self.quic_transport:
                        await self.quic_transport.send_stream_data(
                            peer_addr, stream_id, chunk_msg.to_json().encode("utf-8")
                        )
                    idx += 1
                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=True,
                    result={"streamed_chunks": idx},
                    handled_by=self.name,
                    streamed=True,
                )
                if self.quic_transport:
                    await self.quic_transport.send_stream_data(
                        peer_addr, stream_id, resp.to_json().encode("utf-8")
                    )

            elif inspect.isgeneratorfunction(handler):
                idx = 0
                for chunk in handler(req.payload):
                    chunk_msg = TaskChunk(request_id=req.request_id, index=idx, chunk=chunk)
                    if self.quic_transport:
                        await self.quic_transport.send_stream_data(
                            peer_addr, stream_id, chunk_msg.to_json().encode("utf-8")
                        )
                    idx += 1
                resp = TaskResponse(
                    request_id=req.request_id,
                    ok=True,
                    result={"streamed_chunks": idx},
                    handled_by=self.name,
                    streamed=True,
                )
                if self.quic_transport:
                    await self.quic_transport.send_stream_data(
                        peer_addr, stream_id, resp.to_json().encode("utf-8")
                    )

            elif inspect.iscoroutinefunction(handler):
                result = await handler(req.payload)
                resp = TaskResponse(
                    request_id=req.request_id, ok=True, result=result, handled_by=self.name
                )
                if self.quic_transport:
                    await self.quic_transport.send_stream_data(
                        peer_addr, stream_id, resp.to_json().encode("utf-8")
                    )

            else:
                result = await asyncio.to_thread(handler, req.payload)
                resp = TaskResponse(
                    request_id=req.request_id, ok=True, result=result, handled_by=self.name
                )
                if self.quic_transport:
                    await self.quic_transport.send_stream_data(
                        peer_addr, stream_id, resp.to_json().encode("utf-8")
                    )

        except Exception as exec_err:
            logger.error(f"Erreur QUIC execution '{req.skill}': {exec_err}")
            resp = TaskResponse(
                request_id=req.request_id, ok=False, error=str(exec_err), handled_by=self.name
            )
            if self.quic_transport:
                await self.quic_transport.send_stream_data(
                    peer_addr, stream_id, resp.to_json().encode("utf-8")
                )
        finally:
            if self.quic_transport:
                await self.quic_transport.send_stream_fin(peer_addr, stream_id)
            self._active_tasks = max(0, self._active_tasks - 1)
            self._task_semaphore.release()
