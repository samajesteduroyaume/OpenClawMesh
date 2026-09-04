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
    "http://localhost:8790",
    "http://192.168.1.15:8790",
    "http://82.67.166.90:8790",
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
        self.assigned_ip: str | None = None
        self.rtt_ms: float | None = None
        self.last_seen: float | None = None
        self.last_registration_response: dict[str, Any] | None = None
        self.active_bootstrap_peers: list[dict[str, Any]] = []
        self._heartbeat_task: asyncio.Task | None = None

    async def detect_guichet_endpoint(self) -> str | None:
        """Trouve l'adresse accessible du Guichet Unique Freebox Ultra (test parallèle rapide)."""
        candidates: list[str] = []
        if self.guichet_url:
            candidates.append(self.guichet_url.rstrip("/"))
        for c in DEFAULT_CANDIDATE_URLS:
            if c:
                clean = c.rstrip("/")
                if clean not in candidates:
                    candidates.append(clean)

        async def _check(url: str) -> tuple[str, bool]:
            ok = await self._check_health(url)
            return url, ok

        tasks = [_check(cand) for cand in candidates]
        for coro in asyncio.as_completed(tasks):
            url, ok = await coro
            if ok:
                self.discovered_guichet_url = url
                logger.info(f"✓ Guichet Unique Freebox Ultra détecté sur : {url}")
                return self.discovered_guichet_url

        return None

    async def _check_health(self, base_url: str) -> bool:
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()

        def _probe() -> bool:
            try:
                url = f"{base_url}/api/guichet/health"
                req = urllib.request.Request(url, headers={"User-Agent": "OpenClawMesh-Node/1.0"})
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    return resp.status == 200
            except Exception:
                return False

        ok = await loop.run_in_executor(None, _probe)
        if ok:
            self.rtt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.last_seen = time.time()
        return ok

    def _save_wireguard_config(self, wg_config_text: str) -> None:
        """Sauvegarde la configuration WireGuard reçue pour raccordement direct."""
        try:
            from pathlib import Path
            conf_dir = Path("wireguard_mesh")
            conf_dir.mkdir(parents=True, exist_ok=True)
            conf_file = conf_dir / "wg0.conf"
            conf_file.write_text(wg_config_text, encoding="utf-8")
            logger.info(f"🛡️ Configuration WireGuard auto-enregistrée : {conf_file}")
        except Exception as e:
            logger.debug(f"Impossible de sauvegarder wg0.conf: {e}")

    def _persist_guichet_url(self, url: str) -> None:
        """Enregistre l'URL du Guichet dans .env local pour que les démarrages suivants s'y connectent automatiquement."""
        try:
            from pathlib import Path
            env_path = Path(".env")
            lines = []
            if env_path.exists():
                lines = [l for l in env_path.read_text(encoding="utf-8").splitlines() if not l.startswith("OPENCLAW_FREEBOX_GUICHET_URL=")]
            lines.append(f'OPENCLAW_FREEBOX_GUICHET_URL="{url}"')
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            logger.info(f"💾 URL du Guichet persistée dans .env : {url}")
        except Exception as e:
            logger.debug(f"Impossible de mettre à jour .env: {e}")

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
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                logger.warning(f"Erreur d'enregistrement auprès du Guichet Freebox ({guichet}): {e}")
                return None

        result = await loop.run_in_executor(None, _send_reg)
        if result and result.get("status") == "registered":
            self.is_registered = True
            self.last_registration_response = result
            self.last_seen = time.time()
            self.active_bootstrap_peers = result.get("bootstrap_peers", [])
            logger.info(
                f"🌟 Nœud '{self.name}' enregistré au Guichet Freebox ! "
                f"({len(self.active_bootstrap_peers)} pairs mondiaux reçus pour l'amorçage)"
            )

            # Sauvegarder automatiquement la configuration WireGuard reçue
            wg_prov = result.get("wireguard_provisioning")
            if wg_prov and isinstance(wg_prov, dict):
                self.assigned_ip = wg_prov.get("assigned_ip")
                if wg_prov.get("wg_config"):
                    self._save_wireguard_config(wg_prov["wg_config"])

            # Persister l'URL du Guichet dans .env
            self._persist_guichet_url(guichet)
        return result

    async def auto_onboard_first_start(
        self,
        public_ip: str | None = None,
        nat_type: str = "Full-Cone",
    ) -> dict[str, Any] | None:
        """
        Exécute le raccordement universel 1-clic au Guichet Unique Freebox lors du premier démarrage.
        C'est la toute première action qu'OpenClawMesh effectue pour s'ancrer au maillage mondial.
        """
        from pathlib import Path

        enrolled_marker = Path(".openclaw_enrolled")
        wg_file = Path("wireguard_mesh/wg0.conf")
        is_first_start = not enrolled_marker.exists() or not wg_file.exists()

        # Détecter le matériel si pas encore renseigné
        if not self.hardware:
            try:
                from ..hardware import detect_accelerator
                accel = detect_accelerator()
                self.hardware = accel.to_dict()
                if self.hardware.get("accelerator_type") in ("nvidia_cuda", "apple_silicon_metal", "rocm_amd"):
                    for sk in ("gpu_compute", "llm"):
                        if sk not in self.skills:
                            self.skills.append(sk)
            except Exception:
                pass

        if is_first_start:
            logger.info("🚀 [Premier Démarrage] Raccordement universel 1-clic au Guichet Unique Freebox...")

        res = await self.register(public_ip=public_ip, nat_type=nat_type)
        if res and res.get("status") == "registered":
            try:
                enrolled_marker.write_text(
                    json.dumps({
                        "node_id": self.node_id,
                        "enrolled_at": time.time(),
                        "guichet_url": self.discovered_guichet_url,
                        "assigned_ip": res.get("wireguard_provisioning", {}).get("assigned_ip"),
                    }, indent=2),
                    encoding="utf-8"
                )
            except Exception:
                pass

            if is_first_start:
                logger.info(
                    f"🎉 [Premier Démarrage] Raccordement réussi ! "
                    f"IP WireGuard: {res.get('wireguard_provisioning', {}).get('assigned_ip')} | "
                    f"Hub: {self.discovered_guichet_url}"
                )
        return res

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

    def get_status_summary(self) -> dict[str, Any]:
        """Retourne une synthèse complète de l'état de raccordement au Guichet Unique."""
        return {
            "connected": bool(self.discovered_guichet_url and self.is_registered),
            "guichet_url": self.discovered_guichet_url,
            "is_registered": self.is_registered,
            "assigned_ip": self.assigned_ip,
            "node_id": self.node_id,
            "name": self.name,
            "bootstrap_peers_count": len(self.active_bootstrap_peers),
            "rtt_ms": self.rtt_ms,
            "last_seen": self.last_seen,
        }

    async def dispatch_ai_task(
        self, skill: str, prompt: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Dispatche une tâche IA souveraine via l'orchestrateur du Guichet Unique Freebox."""
        guichet = self.discovered_guichet_url or await self.detect_guichet_endpoint()
        if not guichet:
            return None

        loop = asyncio.get_running_loop()

        def _call_dispatch() -> dict[str, Any] | None:
            try:
                url = f"{guichet}/api/guichet/ai/dispatch"
                payload = {"skill": skill, "prompt": prompt, "params": params or {}}
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "OpenClawMesh-Node/1.0",
                    },
                )
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                logger.debug(f"Erreur dispatch IA Guichet: {e}")
                return None

        return await loop.run_in_executor(None, _call_dispatch)

