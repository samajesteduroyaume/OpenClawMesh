"""
Serveur & Client de Relais WAN WebSocket Sécurisé pour OpenClawMesh.

Permet le transfert de trames chiffrées de bout en bout (E2EE) entre deux pairs
séparés par Internet ou des pare-feux stricts interdisant les connexions P2P directes.
Le serveur relais ne peut jamais déchiffrer le contenu des messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import ssl
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import websockets
from websockets import ServerConnection as WebSocketServerProtocol

from ..config import get_settings

logger = logging.getLogger("openclaw_mesh.relay")
_settings = get_settings()


class WANRelayServer:
    """Serveur relais WAN WebSocket qui route les trames chiffrées sans les inspecter."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        name: str | None = None,
        auth_token: str | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ):
        self.host = host or _settings.relay_host
        self.port = port or _settings.relay_port
        self.name = name or _settings.relay_name
        self.auth_token = auth_token or os.getenv("OPENCLAW_RELAY_AUTH_TOKEN")
        self.ssl_context = ssl_context
        self._server = None
        self._clients: dict[str, WebSocketServerProtocol] = {}  # node_id -> websocket
        self._client_info: dict[str, dict[str, Any]] = {}
        self._running = False
        self._max_clients = max(1, _settings.relay_max_clients)
        self._max_message_bytes = max(1024, _settings.relay_max_message_bytes)

    async def start(self) -> None:
        """Démarre le serveur relais."""
        if self.host not in {"127.0.0.1", "::1", "localhost"}:
            if not self.auth_token:
                raise RuntimeError("Un relais exposé doit définir OPENCLAW_RELAY_AUTH_TOKEN.")
            if not self.ssl_context:
                raise RuntimeError("Un relais WAN exposé doit utiliser TLS avec ssl_context.")
        self._running = True
        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            max_size=self._max_message_bytes,
            ssl=self.ssl_context,
        )
        scheme = "wss" if self.ssl_context else "ws"
        logger.info(f"⚡ Serveur Relais WAN actif sur {scheme}://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Arrête le serveur relais."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for ws in list(self._clients.values()):
            await ws.close()
        self._clients.clear()
        logger.info("Serveur Relais WAN arrêté.")

    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        registered_node_id: str | None = None
        try:
            async for raw_msg in websocket:
                message_size = (
                    len(raw_msg) if isinstance(raw_msg, bytes) else len(raw_msg.encode("utf-8"))
                )
                if message_size > self._max_message_bytes:
                    await websocket.send(json.dumps({"type": "error", "code": "message_too_large"}))
                    await websocket.close(code=1009, reason="message too large")
                    return
                try:
                    data = json.loads(raw_msg)
                except Exception:
                    continue

                msg_type = data.get("type")

                if msg_type != "register" and registered_node_id is None:
                    await websocket.send(
                        json.dumps({"type": "error", "code": "authentication_required"})
                    )
                    continue

                # 1. Enregistrement du nœud
                if msg_type == "register":
                    node_id = data.get("node_id")
                    supplied_token = data.get("auth_token", "")
                    if (
                        node_id
                        and isinstance(node_id, str)
                        and re.fullmatch(r"[A-Za-z0-9_.-]{3,128}", node_id)
                        and (
                            not self.auth_token
                            or (
                                isinstance(supplied_token, str)
                                and secrets.compare_digest(supplied_token, self.auth_token)
                            )
                        )
                    ):
                        if registered_node_id is None and len(self._clients) >= self._max_clients:
                            await websocket.send(
                                json.dumps({"type": "error", "code": "relay_capacity_reached"})
                            )
                            continue
                        if node_id in self._clients and self._clients[node_id] is not websocket:
                            await websocket.send(
                                json.dumps({"type": "error", "code": "node_id_in_use"})
                            )
                            continue
                        registered_node_id = node_id
                        self._clients[node_id] = websocket
                        self._client_info[node_id] = {
                            "name": data.get("name", "anonymous"),
                            "registered_at": time.time(),
                            "remote_addr": str(websocket.remote_address),
                        }
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "registered",
                                    "status": "ok",
                                    "relay_name": self.name,
                                    "active_peers": len(self._clients),
                                }
                            )
                        )
                        logger.info(
                            f"Pair enregistré sur le relais: {node_id} ({self._client_info[node_id]['name']})"
                        )

                # 2. Transfert vers un pair cible (Routage opaque)
                elif msg_type == "forward":
                    target_id = data.get("target_node_id")
                    if target_id and target_id in self._clients:
                        target_ws = self._clients[target_id]
                        forward_packet = {
                            "type": "relayed_message",
                            "sender_node_id": registered_node_id,
                            "payload": data.get("payload"),
                            "timestamp": time.time(),
                        }
                        await target_ws.send(json.dumps(forward_packet))
                    else:
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "peer_not_found",
                                    "target_node_id": target_id,
                                }
                            )
                        )

                # 3. Liste des pairs connectés au relais
                elif msg_type == "list_peers":
                    peers_list = [
                        {"node_id": nid, "name": info["name"]}
                        for nid, info in self._client_info.items()
                        if nid != registered_node_id
                    ]
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "peers_list",
                                "peers": peers_list,
                            }
                        )
                    )

        except Exception as e:
            logger.debug(f"Déconnexion pair relais: {e}")
        finally:
            if registered_node_id and registered_node_id in self._clients:
                del self._clients[registered_node_id]
                self._client_info.pop(registered_node_id, None)
                logger.info(f"Pair retiré du relais: {registered_node_id}")


class WANRelayClient:
    """Client se connectant à un serveur relais WAN pour communiquer avec des pairs distants."""

    def __init__(
        self,
        relay_url: str,
        node_id: str,
        name: str = "openclaw-client",
        auth_token: str | None = None,
    ):
        self.relay_url = relay_url
        self.node_id = node_id
        self.name = name
        self.auth_token = auth_token
        self._ws: Any = None
        self._running = False
        self._incoming_callbacks: list[Callable[[str, Any], None]] = []

    async def connect(self) -> bool:
        """Se connecte au serveur relais et enregistre son identifiant."""
        try:
            parsed = urlparse(self.relay_url)
            if parsed.scheme != "wss" and parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
                raise ValueError("Un relais WAN distant doit utiliser wss://")
            self._ws = await websockets.connect(self.relay_url)
            self._running = True
            # Envoi du message d'enregistrement
            await self._ws.send(
                json.dumps(
                    {
                        "type": "register",
                        "node_id": self.node_id,
                        "name": self.name,
                        "auth_token": self.auth_token,
                    }
                )
            )
            resp = await self._ws.recv()
            data = json.loads(resp)
            if data.get("status") == "ok":
                asyncio.create_task(self._listen_loop())
                return True
        except Exception as e:
            logger.error(f"Échec de connexion au relais WAN {self.relay_url}: {e}")
        return False

    async def disconnect(self) -> None:
        """Ferme la connexion au relais."""
        self._running = False
        if self._ws:
            await self._ws.close()

    async def send_to_peer(self, target_node_id: str, payload: Any) -> None:
        """Envoie un message à un pair distant via le relais."""
        if not self._ws:
            raise RuntimeError("Non connecté au relais WAN.")
        packet = {
            "type": "forward",
            "target_node_id": target_node_id,
            "payload": payload,
        }
        await self._ws.send(json.dumps(packet))

    def on_message(self, callback: Callable[[str, Any], None]) -> None:
        """Enregistre un callback pour les messages entrants (sender_id, payload)."""
        self._incoming_callbacks.append(callback)

    async def _listen_loop(self) -> None:
        try:
            while self._running and self._ws:
                msg = await self._ws.recv()
                data = json.loads(msg)
                if data.get("type") == "relayed_message":
                    sender = data.get("sender_node_id", "")
                    payload = data.get("payload")
                    for cb in self._incoming_callbacks:
                        try:
                            if asyncio.iscoroutinefunction(cb):
                                await cb(sender, payload)
                            else:
                                cb(sender, payload)
                        except Exception as e:
                            logger.error(f"Erreur callback message relais: {e}")
        except Exception:
            pass
