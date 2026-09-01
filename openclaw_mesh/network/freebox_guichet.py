"""
Client d'Enregistrement et d'Amorçage auprès du Guichet Unique Freebox Ultra.

Lorsqu'une machine OpenClawMesh se connecte au maillage, elle s'enregistre
automatiquement auprès de la Freebox Ultra pour :
1. Déposer son adresse IP Publique WAN, son IP Locale LAN, son profil NAT et ses compétences IA.
2. Récupérer instantanément l'annuaire mondial des autres pairs actifs pour s'amorcer.
3. Maintenir un battement de cœur régulier (Keepalive) avec la Freebox.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any

from ..discovery import get_local_ip

logger = logging.getLogger("openclaw_mesh.freebox_guichet")

DEFAULT_CANDIDATE_URLS = [
    os.getenv("OPENCLAW_FREEBOX_GUICHET_URL"),
    "http://127.0.0.1:8790",
    "http://mafreebox.freebox.fr:8790",
    "http://192.168.1.254:8790",
]


class FreeboxGuichetClient:
    """Client asynchrone d'enregistrement et d'interrogation du Guichet Freebox."""

    def __init__(
        self,
        guichet_url: str | None = None,
        node_id: str | None = None,
        name: str | None = None,
        port: int = 8770,
        dht_port: int = 8780,
        skills: list[str] | None = None,
        hardware: dict[str, Any] | None = None,
        pubkey: str | None = None,
        pqc_key: str | None = None,
    ) -> None:
        self.guichet_url = guichet_url
        self.node_id = node_id or f"node-{socket.gethostname()}-{port}"
        self.name = name or socket.gethostname()
        self.port = port
        self.dht_port = dht_port
        self.skills = skills or []
        self.hardware = hardware or {}
        self.pubkey = pubkey
        self.pqc_key = pqc_key

        self.discovered_guichet_url: str | None = None
        self.is_registered: bool = False
        self.active_bootstrap_peers: list[dict[str, Any]] = []
        self._heartbeat_task: asyncio.Task | None = None

    async def detect_guichet_endpoint(self) -> str | None:
        """Trouve l'adresse accessible du Guichet Unique Freebox Ultra."""
        if self.guichet_url:
            if await self._check_health(self.guichet_url):
                self.discovered_guichet_url = self.guichet_url.rstrip("/")
                return self.discovered_guichet_url

        loop = asyncio.get_running_loop()

        for candidate in DEFAULT_CANDIDATE_URLS:
            if not candidate:
                continue
            cand_clean = candidate.rstrip("/")
            if await self._check_health(cand_clean):
                self.discovered_guichet_url = cand_clean
                logger.info(f"✓ Guichet Unique Freebox Ultra détecté sur : {cand_clean}")
                return self.discovered_guichet_url

        return None

    async def _check_health(self, base_url: str) -> bool:
        loop = asyncio.get_running_loop()

        def _probe() -> bool:
            try:
                url = f"{base_url}/api/guichet/health"
                req = urllib.request.Request(url, headers={"User-Agent": "OpenClawMesh-Node/1.0"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    return resp.status == 200
            except Exception:
                return False

        return await loop.run_in_executor(None, _probe)

    async def register(
        self,
        public_ip: str | None = None,
        nat_type: str = "Full-Cone",
        telemetry: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Enregistre ce nœud auprès du Guichet Unique Freebox et récupère les pairs d'amorçage.
        """
        guichet = self.discovered_guichet_url or await self.detect_guichet_endpoint()
        if not guichet:
            logger.debug("Guichet Unique Freebox non joignable (mode autonome).")
            return None

        local_ip = get_local_ip()
        payload = {
            "node_id": self.node_id,
            "name": self.name,
            "local_ip": local_ip,
            "public_ip": public_ip or local_ip,
            "port": self.port,
            "dht_port": self.dht_port,
            "skills": self.skills,
            "hardware": self.hardware,
            "telemetry": telemetry or {},
            "nat_type": nat_type,
            "pubkey": self.pubkey,
            "pqc_key": self.pqc_key,
        }

        loop = asyncio.get_running_loop()

        def _send_reg() -> dict[str, Any] | None:
            try:
                url = f"{guichet}/api/guichet/register"
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data_bytes,
                    headers={"Content-Type": "application/json", "User-Agent": "OpenClawMesh-Node/1.0"},
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                logger.warning(f"Erreur d'enregistrement auprès du Guichet Freebox ({guichet}): {e}")
                return None

        result = await loop.run_in_executor(None, _send_reg)
        if result and result.get("status") == "registered":
            self.is_registered = True
            self.active_bootstrap_peers = result.get("bootstrap_peers", [])
            logger.info(
                f"🌟 Nœud '{self.name}' enregistré au Guichet Freebox ! "
                f"({len(self.active_bootstrap_peers)} pairs mondiaux reçus pour l'amorçage)"
            )
            # Démarrer le battement de cœur
            self.start_heartbeat()
            return result

        return None

    def start_heartbeat(self, interval: float = 30.0) -> None:
        """Démarre la boucle de battement de cœur en tâche de fond."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))

    async def _heartbeat_loop(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            if not self.discovered_guichet_url or not self.is_registered:
                continue

            loop = asyncio.get_running_loop()

            def _send_hb():
                try:
                    url = f"{self.discovered_guichet_url}/api/guichet/heartbeat"
                    payload = {"node_id": self.node_id, "telemetry": {"time": time.time()}}
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=2.0) as resp:
                        return resp.status == 200
                except Exception:
                    return False

            ok = await loop.run_in_executor(None, _send_hb)
            if not ok:
                logger.debug("Heartbeat Guichet Freebox échoué, tentative de réenregistrement...")
                await self.register()

    def stop_heartbeat(self) -> None:
        """Arrête la tâche de battement de cœur."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def fetch_global_ip_directory(self) -> dict[str, Any] | None:
        """Récupère l'annuaire universel complet de toutes les adresses IP du mesh."""
        guichet = self.discovered_guichet_url or await self.detect_guichet_endpoint()
        if not guichet:
            return None

        loop = asyncio.get_running_loop()

        def _get_ips() -> dict[str, Any] | None:
            try:
                url = f"{guichet}/api/guichet/ips"
                req = urllib.request.Request(url, headers={"User-Agent": "OpenClawMesh-Node/1.0"})
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                logger.debug(f"Erreur récupération annuaire IP: {e}")
                return None

        return await loop.run_in_executor(None, _get_ips)
