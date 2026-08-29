"""
Modules Réseau Étendus (WAN, Traversée NAT, Kademlia DHT, Relais) pour OpenClawMesh.
"""

from .dht import Contact, KademliaDHT, RoutingTable, hash_key, xor_distance
from .gossip import GossipProtocol, NodeMetrics
from .gossipsub import ControlMessage, GossipMessage, GossipSubNode, MessageCache
from .ice import ICECandidate, ICENegotiator
from .nat_traversal import NATProfile, discover_nat_and_public_ip
from .onion import OnionHop, OnionPacket, OnionRouter
from .quic_webrtc import (
    PacketFlags,
    PacketType,
    QUICPacket,
    QUICSession,
    QUICStream,
    QUICWebRTCTransport,
)
from .relay import WANRelayClient, WANRelayServer
from .skademlia import (
    SKademliaIdentity,
    SKademliaNodeValidator,
    SKademliaPuzzleSolver,
)
from .webrtc import (
    ICEServerConfig,
    WebRTCChannel,
    WebRTCDataChannelConfig,
    WebRTCSessionDescription,
    WebRTCSignalingManager,
)

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
    "GossipProtocol",
    "NodeMetrics",
    "GossipSubNode",
    "GossipMessage",
    "ControlMessage",
    "MessageCache",
    "ICECandidate",
    "ICENegotiator",
    "QUICWebRTCTransport",
    "QUICStream",
    "QUICSession",
    "QUICPacket",
    "PacketType",
    "PacketFlags",
    "WebRTCChannel",
    "WebRTCSignalingManager",
    "WebRTCSessionDescription",
    "WebRTCDataChannelConfig",
    "ICEServerConfig",
    "OnionRouter",
    "OnionPacket",
    "OnionHop",
    "SKademliaPuzzleSolver",
    "SKademliaNodeValidator",
    "SKademliaIdentity",
]

