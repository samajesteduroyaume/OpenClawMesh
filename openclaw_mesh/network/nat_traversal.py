"""
Module de Traversée NAT & Détection STUN pour OpenClawMesh.

Détermine automatiquement l'adresse IP publique et le port externe du nœud
pour établir des liaisons directes P2P à travers les pare-feux et routeurs (NAT).
"""
from __future__ import annotations
import asyncio
import logging
import socket
import struct
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger("openclaw_mesh.nat")

# Serveurs STUN publics standards (RFC 5389)
DEFAULT_STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
    ("stun1.l.google.com", 19302),
]


@dataclass
class NATProfile:
    public_ip: Optional[str]
    public_port: Optional[int]
    local_ip: str
    local_port: int
    nat_type: str  # "Open/Public", "Full-Cone", "Restricted", "Symmetric", "Blocked/Unknown"
    is_direct_connectable: bool = False


async def discover_nat_and_public_ip(
    local_port: int = 8770,
    stun_servers: list[tuple[str, int]] = DEFAULT_STUN_SERVERS,
    timeout: float = 2.0,
) -> NATProfile:
    """
    Envoie une requête STUN Binding (RFC 5389) pour déterminer l'IP publique et le port mappé.
    """
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    for host, port in stun_servers:
        try:
            # Construction d'un paquet STUN Binding Request standard (20 octets)
            # Type: 0x0001 (Binding Request), Length: 0x0000, Magic Cookie: 0x2112A442, Transaction ID: 12 bytes
            trans_id = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0\x11\x22\x33\x44"
            magic_cookie = b"\x21\x12\xa4\x42"
            stun_header = struct.pack("!HHI", 0x0001, 0, 0x2112A442) + trans_id

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.bind(("", 0))
            sock.sendto(stun_header, (host, port))

            data, addr = sock.recvfrom(2048)
            sock.close()

            # Analyse de la réponse STUN (Type 0x0101 = Binding Success)
            msg_type, msg_len, cookie = struct.unpack("!HHI", data[:8])
            if msg_type == 0x0101:
                # Recherche de l'attribut XOR-MAPPED-ADDRESS (0x0020) ou MAPPED-ADDRESS (0x0001)
                idx = 20
                while idx < len(data):
                    attr_type, attr_len = struct.unpack("!HH", data[idx:idx+4])
                    if attr_type == 0x0020:  # XOR-MAPPED-ADDRESS
                        x_family, x_port = struct.unpack("!BBH", data[idx+4:idx+8])
                        xor_port = x_port ^ 0x2112
                        xor_ip_bytes = data[idx+8:idx+12]
                        real_ip_bytes = bytes(b ^ m for b, m in zip(xor_ip_bytes, magic_cookie))
                        pub_ip = socket.inet_ntoa(real_ip_bytes)
                        
                        return NATProfile(
                            public_ip=pub_ip,
                            public_port=xor_port,
                            local_ip=local_ip,
                            local_port=local_port,
                            nat_type="Cone NAT (P2P Traversal Compatible)",
                            is_direct_connectable=True,
                        )
                    idx += 4 + attr_len
        except Exception as e:
            logger.debug(f"Échec tentative STUN sur {host}:{port} : {e}")

    # Fallback si STUN est bloqué ou inaccessible
    return NATProfile(
        public_ip=None,
        public_port=None,
        local_ip=local_ip,
        local_port=local_port,
        nat_type="Symmetric / Firewall (Relay Required)",
        is_direct_connectable=False,
    )
