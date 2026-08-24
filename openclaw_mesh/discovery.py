"""
Module de découverte réseau mDNS/Zeroconf pour OpenClawMesh.

Découvre automatiquement les nœuds JarvisMesh et OpenClawMesh sur le LAN,
et publie l'identité et les compétences du nœud local.
"""
from __future__ import annotations
import asyncio
import socket
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from zeroconf import IPVersion, ServiceStateChange
from zeroconf.asyncio import AsyncZeroconf, AsyncServiceInfo, AsyncServiceBrowser

from .protocol import (
    SERVICE_TYPE_JARVISMESH,
    SERVICE_TYPE_OPENCLAW,
    SERVICE_TYPES,
)


def get_local_ip() -> str:
    """Détecte l'adresse IP locale principale utilisable sur le LAN."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


@dataclass
class PeerInfo:
    """Informations sur un pair découvert sur le réseau maillé."""
    name: str
    address: str
    port: int
    skills: list[str] = field(default_factory=list)
    service_type: str = SERVICE_TYPE_JARVISMESH
    last_seen: float = field(default_factory=time.time)
    health: Optional[dict] = None
    rtt_ms: Optional[float] = None

    @property
    def ws_url(self) -> str:
        return f"ws://{self.address}:{self.port}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "address": self.address,
            "port": self.port,
            "ws_url": self.ws_url,
            "skills": self.skills,
            "service_type": self.service_type,
            "last_seen": self.last_seen,
            "health": self.health,
            "rtt_ms": self.rtt_ms,
        }


class MeshDiscovery:
    """Gestionnaire de découverte asynchrone mDNS pour OpenClawMesh."""

    def __init__(
        self,
        node_name: Optional[str] = None,
        port: Optional[int] = None,
        skills: Optional[list[str]] = None,
        advertise_ip: Optional[str] = None,
        on_peer_changed: Optional[Callable[[str, Optional[PeerInfo]], None]] = None,
        service_types: Optional[list[str]] = None,
    ):
        self.node_name = node_name
        self.port = port
        self.skills = skills or []
        self.advertise_ip = advertise_ip or get_local_ip()
        self.on_peer_changed = on_peer_changed
        self.service_types = service_types or SERVICE_TYPES

        self.peers: dict[str, PeerInfo] = {}
        self._zc: Optional[AsyncZeroconf] = None
        self._service_infos: list[AsyncServiceInfo] = []
        self._browsers: list[AsyncServiceBrowser] = []
        self._running = False

    async def start(self, advertise: bool = True) -> None:
        """Démarre Zeroconf et l'écoute des services réseau."""
        if self._running:
            return

        self._zc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        self._running = True

        # 1. Annoncer ce nœud si configuré
        if advertise and self.node_name and self.port:
            skills_txt = ",".join(self.skills)
            for stype in self.service_types:
                svc_name = f"{self.node_name}.{stype}"
                info = AsyncServiceInfo(
                    stype,
                    svc_name,
                    addresses=[socket.inet_aton(self.advertise_ip)],
                    port=self.port,
                    properties={"skills": skills_txt, "proto": "1.0", "client": "openclaw"},
                )
                await self._zc.async_register_service(info)
                self._service_infos.append(info)

        # 2. Écouter les types de services
        for stype in self.service_types:
            browser = AsyncServiceBrowser(
                self._zc.zeroconf,
                stype,
                handlers=[self._on_service_state_change]
            )
            self._browsers.append(browser)

    async def stop(self) -> None:
        """Arrête la découverte et désenregistre les services."""
        if not self._running:
            return
        self._running = False

        for b in self._browsers:
            await b.async_cancel()
        self._browsers.clear()

        if self._zc:
            for sinfo in self._service_infos:
                try:
                    await self._zc.async_unregister_service(sinfo)
                except Exception:
                    pass
            self._service_infos.clear()
            await self._zc.async_close()
            self._zc = None

    def _on_service_state_change(self, zeroconf, service_type: str, name: str, state_change: ServiceStateChange) -> None:
        peer_name = name
        for st in SERVICE_TYPES:
            if peer_name.endswith(f".{st}"):
                peer_name = peer_name[:-len(f".{st}")]
                break

        if self.node_name and peer_name == self.node_name:
            return

        if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
            asyncio.ensure_future(self._resolve_peer(zeroconf, service_type, name, peer_name))
        elif state_change == ServiceStateChange.Removed:
            removed = self.peers.pop(peer_name, None)
            if removed and self.on_peer_changed:
                self.on_peer_changed(peer_name, None)

    async def _resolve_peer(self, zeroconf, service_type: str, name: str, peer_name: str) -> None:
        info = AsyncServiceInfo(service_type, name)
        ok = await info.async_request(zeroconf, 3000)
        if not ok or not info.addresses:
            return

        address = socket.inet_ntoa(info.addresses[0])
        skills_raw = info.properties.get(b"skills", b"").decode("utf-8", errors="ignore")
        skills_list = [s.strip() for s in skills_raw.split(",") if s.strip()]

        peer = PeerInfo(
            name=peer_name,
            address=address,
            port=info.port,
            skills=skills_list,
            service_type=service_type,
            last_seen=time.time(),
        )
        self.peers[peer_name] = peer

        if self.on_peer_changed:
            self.on_peer_changed(peer_name, peer)

    def add_static_peer(self, name: str, address: str, port: int, skills: Optional[list[str]] = None) -> PeerInfo:
        """Ajoute manuellement un pair (pratique en environnement sans multicast)."""
        peer = PeerInfo(
            name=name,
            address=address,
            port=port,
            skills=skills or [],
            service_type="static",
            last_seen=time.time(),
        )
        self.peers[name] = peer
        return peer

    def list_peers(self) -> dict[str, PeerInfo]:
        return dict(self.peers)

    def find_peers_for_skill(self, skill: str) -> list[PeerInfo]:
        return [p for p in self.peers.values() if skill in p.skills]


async def scan_mesh_peers(timeout: float = 2.5, service_types: Optional[list[str]] = None) -> dict[str, PeerInfo]:
    """Effectue un scan réseau ponctuel pour découvrir les pairs actifs."""
    discovery = MeshDiscovery(service_types=service_types)
    await discovery.start(advertise=False)
    await asyncio.sleep(timeout)
    peers = discovery.list_peers()
    await discovery.stop()
    return peers
