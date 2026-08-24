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
import time
from typing import Any, Callable, Dict, Optional, Set
import websockets
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger("openclaw_mesh.relay")


class WANRelayServer:
    """Serveur relais WAN WebSocket qui route les trames chiffrées sans les inspecter."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8790, name: str = "openclaw-wan-relay"):
        self.host = host
        self.port = port
        self.name = name
        self._server = None
        self._clients: dict[str, WebSocketServerProtocol] = {}  # node_id -> websocket
        self._client_info: dict[str, dict[str, Any]] = {}
        self._running = False

    async def start(self) -> None:
        """Démarre le serveur relais."""
        self._running = True
        self._server = await websockets.serve(self._handle_client, self.host, self.port)
        logger.info(f"⚡ Serveur Relais WAN actif sur ws://{self.host}:{self.port}")

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
        registered_node_id: Optional[str] = None
        try:
            async for raw_msg in websocket:
                try:
                    data = json.loads(raw_msg)
                except Exception:
                    continue

                msg_type = data.get("type")

                # 1. Enregistrement du nœud
                if msg_type == "register":
                    node_id = data.get("node_id")
                    if node_id:
                        registered_node_id = node_id
                        self._clients[node_id] = websocket
                        self._client_info[node_id] = {
                            "name": data.get("name", "anonymous"),
                            "registered_at": time.time(),
                            "remote_addr": str(websocket.remote_address),
                        }
                        await websocket.send(json.dumps({
                            "type": "registered",
                            "status": "ok",
                            "relay_name": self.name,
                            "active_peers": len(self._clients),
                        }))
                        logger.info(f"Pair enregistré sur le relais: {node_id} ({self._client_info[node_id]['name']})")

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
                        await websocket.send(json.dumps({
                            "type": "error",
                            "code": "peer_not_found",
                            "target_node_id": target_id,
                        }))

                # 3. Liste des pairs connectés au relais
                elif msg_type == "list_peers":
                    peers_list = [
                        {"node_id": nid, "name": info["name"]}
                        for nid, info in self._client_info.items()
                        if nid != registered_node_id
                    ]
                    await websocket.send(json.dumps({
                        "type": "peers_list",
                        "peers": peers_list,
                    }))

        except Exception as e:
            logger.debug(f"Déconnexion pair relais: {e}")
        finally:
            if registered_node_id and registered_node_id in self._clients:
                del self._clients[registered_node_id]
                self._client_info.pop(registered_node_id, None)
                logger.info(f"Pair retiré du relais: {registered_node_id}")


class WANRelayClient:
    """Client se connectant à un serveur relais WAN pour communiquer avec des pairs distants."""

    def __init__(self, relay_url: str, node_id: str, name: str = "openclaw-client"):
        self.relay_url = relay_url
        self.node_id = node_id
        self.name = name
        self._ws = None
        self._running = False
        self._incoming_callbacks: list[Callable[[str, Any], None]] = []

    async def connect(self) -> bool:
        """Se connecte au serveur relais et enregistre son identifiant."""
        try:
            self._ws = await websockets.connect(self.relay_url)
            self._running = True
            # Envoi du message d'enregistrement
            await self._ws.send(json.dumps({
                "type": "register",
                "node_id": self.node_id,
                "name": self.name,
            }))
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
