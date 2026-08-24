"""
Modules Réseau Étendus (WAN, Traversée NAT, Kademlia DHT, Relais) pour OpenClawMesh.
"""
from .nat_traversal import discover_nat_and_public_ip, NATProfile
from .relay import WANRelayServer, WANRelayClient
from .dht import KademliaDHT, Contact, RoutingTable, hash_key, xor_distance

__all__ = [
    "discover_nat_and_public_ip",
    "NATProfile",
    "WANRelayServer",
    "WANRelayClient",
    "KademliaDHT",
    "Contact",
    "RoutingTable",
    "hash_key",
    "xor_distance",
]
