"""Modules Réseau Étendus (WAN, Traversée NAT, Kademlia DHT, Relais, FEC, Multipath) pour OpenClawMesh."""

from .binary_framing import BinaryFrame, FastBinaryStreamCodec
from .dht import Contact, KademliaDHT, RoutingTable, hash_key, xor_distance
from .dht_rendezvous import DHTRendezvousManager, RendezvousRecord
from .fec import FECBlock, FECDecoder, FECEncoder
from .federation import FederationBridge, MeshDomain
from .gossip import GossipProtocol, NodeMetrics
from .gossipsub import ControlMessage, GossipMessage, GossipSubNode, MessageCache
from .ice import ICECandidate, ICENegotiator
from .ipv6_pcp import IPv6Detector, NATPMPClient, PCPClient, PortMappingResult
from .multipath_routing import MultipathRouter, PathMetrics, SelfHealingController
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
from .session_failover import SessionFailoverController, SessionStateSnapshot
from .skademlia import (
    SKademliaIdentity,
    SKademliaNodeValidator,
    SKademliaPuzzleSolver,
)
from .traffic_shaping import MultipathOnionSharder, PaddedPacket, TrafficShaper
from .webrtc import (
    ICEServerConfig,
    WebRTCChannel,
    WebRTCDataChannelConfig,
    WebRTCSessionDescription,
    WebRTCSignalingManager,
)

__all__ = [
    "Contact",
    "ControlMessage",
    "DHTRendezvousManager",
    "FECBlock",
    "FECDecoder",
    "FECEncoder",
    "FederationBridge",
    "GossipMessage",
    "GossipProtocol",
    "GossipSubNode",
    "ICECandidate",
    "ICENegotiator",
    "ICEServerConfig",
    "IPv6Detector",
    "KademliaDHT",
    "MessageCache",
    "MeshDomain",
    "MultipathOnionSharder",
    "MultipathRouter",
    "NATPMPClient",
    "NATProfile",
    "NodeMetrics",
    "OnionHop",
    "OnionPacket",
    "OnionRouter",
    "PCPClient",
    "PacketFlags",
    "PacketType",
    "PaddedPacket",
    "PathMetrics",
    "PortMappingResult",
    "QUICPacket",
    "QUICSession",
    "QUICStream",
    "QUICWebRTCTransport",
    "RendezvousRecord",
    "RoutingTable",
    "SKademliaIdentity",
    "SKademliaNodeValidator",
    "SKademliaPuzzleSolver",
    "SelfHealingController",
    "SessionFailoverController",
    "SessionStateSnapshot",
    "TrafficShaper",
    "WANRelayClient",
    "WANRelayServer",
    "WebRTCChannel",
    "WebRTCDataChannelConfig",
    "WebRTCSessionDescription",
    "WebRTCSignalingManager",
    "discover_nat_and_public_ip",
    "hash_key",
    "xor_distance",
]
