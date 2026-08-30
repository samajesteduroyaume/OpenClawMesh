"""
Module de Traversée NAT, Détection STUN & Mappage UPnP pour OpenClawMesh.

Détermine automatiquement l'adresse IP publique et le port externe du nœud,
et ouvre automatiquement les ports sur la passerelle (UPnP IGD / NAT-PMP)
pour établir des liaisons directes P2P à travers le Web.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import socket
import struct
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

logger = logging.getLogger("openclaw_mesh.nat")

# Serveurs STUN publics standards (RFC 5389)
DEFAULT_STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
    ("stun1.l.google.com", 19302),
    ("stun2.l.google.com", 19302),
]


@dataclass
class NATProfile:
    public_ip: str | None
    public_port: int | None
    local_ip: str
    local_port: int
    nat_type: str  # "Open/Public", "Full-Cone", "Restricted", "Symmetric", "Blocked/Unknown", "UPnP Mapped"
    is_direct_connectable: bool = False
    upnp_mapped: bool = False


async def auto_map_upnp_port(
    local_port: int,
    external_port: int | None = None,
    protocol: str = "TCP",
    description: str = "OpenClawMesh P2P",
    lease_duration: int = 86400,
) -> bool:
    """
    Tente d'ouvrir et de mapper automatiquement un port sur le routeur/passerelle
    via le protocole UPnP IGD (InternetGatewayDevice).
    """
    external_port = external_port or local_port
    protocol = protocol.upper()

    loop = asyncio.get_running_loop()

    def _sync_upnp_map() -> bool:
        try:
            # 1. Découverte SSDP de la passerelle UPnP
            ssdp_req = (
                b"M-SEARCH * HTTP/1.1\r\n"
                b"HOST: 239.255.255.250:1900\r\n"
                b'MAN: "ssdp:discover"\r\n'
                b"MX: 2\r\n"
                b"ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n"
                b"\r\n"
            )

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.settimeout(1.5)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            try:
                sock.sendto(ssdp_req, ("239.255.255.250", 1900))
                data, _ = sock.recvfrom(4096)
            except Exception:
                return False
            finally:
                sock.close()

            # Extraire le header LOCATION
            response_text = data.decode("utf-8", errors="ignore")
            location_url = None
            for line in response_text.splitlines():
                if line.lower().startswith("location:"):
                    location_url = line.split(":", 1)[1].strip()
                    break

            if not location_url:
                return False

            # 2. Récupérer le XML de description du routeur
            req = urllib.request.Request(location_url, headers={"User-Agent": "OpenClawMesh"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                xml_content = resp.read()

            root = ET.fromstring(xml_content)
            control_url = None
            service_type = None

            # Chercher WANIPConnection ou WANPPPConnection
            for service in root.iter("{urn:schemas-upnp-org:device-1-0}service"):
                st_el = service.find("{urn:schemas-upnp-org:device-1-0}serviceType")
                cu_el = service.find("{urn:schemas-upnp-org:device-1-0}controlURL")
                if st_el is not None and cu_el is not None and st_el.text:
                    if "WANIPConnection" in st_el.text or "WANPPPConnection" in st_el.text:
                        service_type = st_el.text
                        control_url = cu_el.text
                        break

            if not control_url or not service_type:
                return False

            # Construire l'URL de contrôle absolue
            if not control_url.startswith("http"):
                base_parts = location_url.split("/", 3)
                base_url = f"{base_parts[0]}//{base_parts[2]}"
                control_url = base_url + ("" if control_url.startswith("/") else "/") + control_url

            # Obtenir l'IP locale réelle
            s_ip = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s_ip.connect(("8.8.8.8", 80))
                my_local_ip = s_ip.getsockname()[0]
            finally:
                s_ip.close()

            # 3. Envoyer la requête SOAP AddPortMapping
            soap_body = f"""<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
<s:Body>
<u:AddPortMapping xmlns:u="{service_type}">
<NewRemoteHost></NewRemoteHost>
<NewExternalPort>{external_port}</NewExternalPort>
<NewProtocol>{protocol}</NewProtocol>
<NewInternalPort>{local_port}</NewInternalPort>
<NewInternalClient>{my_local_ip}</NewInternalClient>
<NewEnabled>1</NewEnabled>
<NewPortMappingDescription>{description}</NewPortMappingDescription>
<NewLeaseDuration>{lease_duration}</NewLeaseDuration>
</u:AddPortMapping>
</s:Body>
</s:Envelope>"""

            soap_headers = {
                "SOAPAction": f'"{service_type}#AddPortMapping"',
                "Content-Type": 'text/xml; charset="utf-8"',
                "Content-Length": str(len(soap_body.encode("utf-8"))),
                "User-Agent": "OpenClawMesh",
            }

            req_soap = urllib.request.Request(
                control_url, data=soap_body.encode("utf-8"), headers=soap_headers
            )
            with urllib.request.urlopen(req_soap, timeout=2.5) as resp_soap:
                if resp_soap.status in (200, 204):
                    logger.info(
                        f"✓ Port UPnP ouvert avec succès : Extérieur {external_port}/{protocol} -> {my_local_ip}:{local_port}"
                    )
                    return True
            return False
        except Exception as e:
            logger.debug(f"Tentative UPnP non disponible sur ce réseau : {e}")
            return False

    return await loop.run_in_executor(None, _sync_upnp_map)


async def discover_nat_and_public_ip(
    local_port: int = 8770,
    stun_servers: list[tuple[str, int]] = DEFAULT_STUN_SERVERS,
    timeout: float = 2.0,
    enabled: bool = False,
    try_upnp: bool = False,
) -> NATProfile:
    """
    Envoie une requête STUN Binding (RFC 5389) et teste UPnP pour déterminer l'IP publique et le port mappé.
    Cette fonction est strictement opt-in (désactivée par défaut) et requiert le consentement explicite.
    """
    local_ip = "127.0.0.1"
    if not enabled:
        return NATProfile(
            public_ip=None,
            public_port=None,
            local_ip=local_ip,
            local_port=local_port,
            nat_type="Local Only (LAN default)",
            is_direct_connectable=False,
            upnp_mapped=False,
        )
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    upnp_success = False
    if try_upnp:
        upnp_success = await auto_map_upnp_port(local_port=local_port, external_port=local_port)

    for host, port in stun_servers:
        try:
            # Construction d'un paquet STUN Binding Request standard (20 octets)
            trans_id = secrets.token_bytes(12)
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
                idx = 20
                while idx < len(data):
                    attr_type, attr_len = struct.unpack("!HH", data[idx : idx + 4])
                    if attr_type == 0x0020:  # XOR-MAPPED-ADDRESS
                        x_family, x_port = struct.unpack("!BBH", data[idx + 4 : idx + 8])
                        xor_port = x_port ^ 0x2112
                        xor_ip_bytes = data[idx + 8 : idx + 12]
                        real_ip_bytes = bytes(
                            b ^ m for b, m in zip(xor_ip_bytes, magic_cookie, strict=True)
                        )
                        pub_ip = socket.inet_ntoa(real_ip_bytes)

                        return NATProfile(
                            public_ip=pub_ip,
                            public_port=local_port if upnp_success else xor_port,
                            local_ip=local_ip,
                            local_port=local_port,
                            nat_type="UPnP Mapped"
                            if upnp_success
                            else "Cone NAT (P2P Traversal Compatible)",
                            is_direct_connectable=True,
                            upnp_mapped=upnp_success,
                        )
                    idx += 4 + attr_len
        except Exception as e:
            logger.debug(f"Échec tentative STUN sur {host}:{port} : {e}")

    # Fallback si STUN ne répond pas
    return NATProfile(
        public_ip=None,
        public_port=None,
        local_ip=local_ip,
        local_port=local_port,
        nat_type="Symmetric / Firewall (Relay Required)",
        is_direct_connectable=False,
        upnp_mapped=False,
    )
