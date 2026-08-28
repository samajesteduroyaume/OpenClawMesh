"""
Modules Réseau Étendus (WAN, Traversée NAT, Kademlia DHT, Relais) pour OpenClawMesh.
"""

from .dht import Contact, KademliaDHT, RoutingTable, hash_key, xor_distance
from .nat_traversal import NATProfile, discover_nat_and_public_ip
from .relay import WANRelayClient, WANRelayServer

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
