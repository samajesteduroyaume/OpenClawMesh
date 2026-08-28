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

        self.discovery: MeshDiscovery | None = None
        self._ws_server = None
        self._active_tasks = 0
        self._task_semaphore = asyncio.Semaphore(max(1, _settings.max_active_tasks))
        self._queue_semaphore = asyncio.Semaphore(
            max(1, _settings.max_active_tasks + _settings.max_queued_tasks)
        )
        self._start_time = time.time()
        self._running = False

    async def start(self, enable_zeroconf: bool = False) -> None:
        """Démarre le serveur WebSocket et la publication Zeroconf."""
        if self._running:
            return
        if self.host not in {"127.0.0.1", "::1", "localhost"}:
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
        self._ws_server = await websockets.serve(
            self._handle_ws,
            self.host,
            self.port,
            ssl=self.ssl_context,
            max_size=16 * 1024 * 1024,
        )
        self._running = True

        if enable_zeroconf:
            skills_list = self.registry.list_remote_names()
            self.discovery = MeshDiscovery(
                node_name=self.name,
                port=self.port,
                skills=skills_list,
                advertise_ip=self.advertise_ip,
            )
            await self.discovery.start(advertise=True)

        logger.info(f"Nœud OpenClawMesh '{self.name}' démarré sur {self.host}:{self.port}")

    async def stop(self) -> None:
        """Arrête le serveur et la découverte réseau."""
        if not self._running:
            return
        self._running = False

        if self.discovery:
            await self.discovery.stop()
            self.discovery = None

        if self._ws_server:
            try:
                self._ws_server.close()
                await self._ws_server.wait_closed()
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
                if not self._queue_semaphore.locked():
                    await self._queue_semaphore.acquire()
                    asyncio.create_task(self._process_message_with_timeout(ws, raw, send_lock))
                else:
                    await ws.close(code=1013, reason="Capacité du nœud atteinte")
                    break
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

        if self._task_semaphore.locked():
            resp = TaskResponse(
                request_id=req.request_id,
                ok=False,
                error="Capacité du nœud atteinte",
                handled_by=self.name,
            )
            async with send_lock:
                await ws.send(resp.to_json())
            return
        await self._task_semaphore.acquire()
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
