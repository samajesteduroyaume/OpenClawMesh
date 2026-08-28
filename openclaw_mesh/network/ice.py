"""
Module de Négociation ICE (Interactive Connectivity Establishment) pour OpenClawMesh (RFC 8445).

Découvre, échange et sélectionne le meilleur chemin réseau direct entre deux pairs :
1. 🏠 Host Candidates (Adresses IP locales LAN directes)
2. 🌐 Server Reflexive / STUN Candidates (IP & Port publics réflexifs)
3. 🛡️ Relayed / TURN Candidates (Serveurs relais WebSocket E2EE sécurisés)
"""

from __future__ import annotations

import logging
import secrets
import socket
import time
from dataclasses import asdict, dataclass
from typing import Any

from ..config import get_settings
from .nat_traversal import discover_nat_and_public_ip

logger = logging.getLogger("openclaw_mesh.ice")
_settings = get_settings()

# Priorités standards ICE
PRIORITY_HOST = 2130706431      # 2^24 * 126 + ...
PRIORITY_SRFLX = 1694498815     # 2^24 * 100 + ...
PRIORITY_RELAY = 16777215       # 2^24 * 0 + ...


@dataclass
class ICECandidate:
    """Représente un candidat de transport réseau pour la connectivité P2P."""

    foundation: str
    component: int  # 1 = RTP/Data
    protocol: str   # "udp" ou "tcp"
    priority: int
    ip: str
    port: int
    type: str       # "host", "srflx", "prflx", "relay"
    related_address: str | None = None
    related_port: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ICECandidate:
        return cls(
            foundation=str(data.get("foundation", "")),
            component=int(data.get("component", 1)),
            protocol=str(data.get("protocol", "udp")).lower(),
            priority=int(data.get("priority", 0)),
            ip=str(data.get("ip", "127.0.0.1")),
            port=int(data.get("port", 0)),
            type=str(data.get("type", "host")),
            related_address=data.get("related_address"),
            related_port=data.get("related_port"),
        )

    def to_sdp_string(self) -> str:
        """Formate le candidat selon la syntaxe SDP RFC 5245."""
        base = (
            f"candidate:{self.foundation} {self.component} {self.protocol.upper()} "
            f"{self.priority} {self.ip} {self.port} typ {self.type}"
        )
        if self.related_address and self.related_port:
            base += f" raddr {self.related_address} rport {self.related_port}"
        return base


@dataclass
class ICECandidatePair:
    """Paire ordonnée (candidat local, candidat distant) évaluée lors des checks de connectivité."""

    local: ICECandidate
    remote: ICECandidate
    state: str = "frozen"  # "frozen", "waiting", "in-progress", "succeeded", "failed"
    rtt_ms: float | None = None

    @property
    def priority(self) -> int:
        """Calcul de priorité de paire selon la formule RFC 8445."""
        g = self.local.priority
        d = self.remote.priority
        return (2**32 * min(g, d)) + (2 * max(g, d)) + (1 if g > d else 0)


class ICENegotiator:
    """Moteur de collecte de candidats et de négociation de connectivité P2P."""

    def __init__(
        self,
        local_name: str = "node",
        local_port: int = 8770,
        relay_url: str | None = None,
    ):
        self.local_name = local_name
        self.local_port = local_port
        self.relay_url = relay_url
        self.ufrag = secrets.token_hex(4)
        self.pwd = secrets.token_hex(12)
        self.candidates: list[ICECandidate] = []

    async def gather_candidates(self) -> list[ICECandidate]:
        """Collecte automatiquement tous les candidats locaux, STUN et relais."""
        self.candidates.clear()
        foundation_idx = 1

        # 1. Host Candidates (Interfaces locales)
        local_ips = self._get_local_interfaces()
        for ip in local_ips:
            cand = ICECandidate(
                foundation=f"f{foundation_idx}",
                component=1,
                protocol="tcp" if ip == "127.0.0.1" else "udp",
                priority=PRIORITY_HOST - foundation_idx * 100,
                ip=ip,
                port=self.local_port,
                type="host",
            )
            self.candidates.append(cand)
            foundation_idx += 1

        # 2. Server Reflexive Candidates (STUN / UPnP via nat_traversal)
        try:
            nat_prof = await discover_nat_and_public_ip(local_port=self.local_port)
            if nat_prof.public_ip and nat_prof.public_port:
                srflx_cand = ICECandidate(
                    foundation=f"f{foundation_idx}",
                    component=1,
                    protocol="udp",
                    priority=PRIORITY_SRFLX,
                    ip=nat_prof.public_ip,
                    port=nat_prof.public_port,
                    type="srflx",
                    related_address=nat_prof.local_ip,
                    related_port=nat_prof.local_port,
                )
                self.candidates.append(srflx_cand)
                foundation_idx += 1
        except Exception as e:
            logger.debug(f"Découverte STUN/NAT pour ICE échouée: {e}")

        # 3. Relayed Candidate (TURN / WebSocket Relay)
        if self.relay_url:
            relay_cand = ICECandidate(
                foundation=f"f{foundation_idx}",
                component=1,
                protocol="tcp",
                priority=PRIORITY_RELAY,
                ip=self.relay_url,
                port=443,
                type="relay",
            )
            self.candidates.append(relay_cand)

        # Trier par priorité décroissante
        self.candidates.sort(key=lambda c: c.priority, reverse=True)
        return list(self.candidates)

    def create_offer(self) -> dict[str, Any]:
        """Crée l'offre ICE à échanger avec le pair."""
        return {
            "ufrag": self.ufrag,
            "pwd": self.pwd,
            "candidates": [c.to_dict() for c in self.candidates],
            "ts": time.time(),
        }

    def select_best_candidate_pair(
        self, remote_offer: dict[str, Any]
    ) -> tuple[ICECandidate, ICECandidate] | None:
        """
        Forme la matrice des paires de candidats et sélectionne le chemin optimal
        (Direct Host > Reflexive STUN > Fallback Relay).
        """
        remote_cands_raw = remote_offer.get("candidates", [])
        remote_candidates = [ICECandidate.from_dict(c) for c in remote_cands_raw]
        if not self.candidates or not remote_candidates:
            return None

        pairs: list[ICECandidatePair] = []
        for local_c in self.candidates:
            for remote_c in remote_candidates:
                # Éviter les combinaisons incompatibles (ex: host loopback avec host publique)
                if local_c.type == "host" and local_c.ip == "127.0.0.1" and remote_c.ip != "127.0.0.1":
                    continue
                pair = ICECandidatePair(local=local_c, remote=remote_c)
                pairs.append(pair)

        if not pairs:
            # Fallback direct premier candidat disponible
            return self.candidates[0], remote_candidates[0]

        # Trier par priorité maximale RFC 8445
        pairs.sort(key=lambda p: p.priority, reverse=True)
        best_pair = pairs[0]
        return best_pair.local, best_pair.remote

    @staticmethod
    def _get_local_interfaces() -> list[str]:
        """Récupère les adresses IP IPv4 de toutes les interfaces réseau actives."""
        ips = {"127.0.0.1"}
        try:
            # Socket datagram test
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
            s.close()
        except Exception:
            pass
        return sorted(ips)
