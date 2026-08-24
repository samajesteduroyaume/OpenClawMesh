"""
OpenClawMesh — Protocole P2P & Skill Décentralisé pour OpenClaw.

100% compatible avec JarvisMesh 1.0.
Permet la découverte locale mDNS, le routage DHT Kademlia, la traversée NAT & Relais WAN,
le chiffrement de bout en bout (E2EE), la délégation multi-matériels (NVIDIA, AMD, Intel, Apple)
et l'inférence multi-modale (Vision, Whisper STT, TTS, MoE).
"""

__version__ = "1.0.0"

from .protocol import (
    PROTOCOL_VERSION,
    SERVICE_TYPE_JARVISMESH,
    SERVICE_TYPE_OPENCLAW,
    TaskRequest,
    TaskChunk,
    TaskResponse,
    sign_request,
    verify_request,
    parse_message,
)
from .crypto import NodeIdentity, TrustStore, verify_ed25519_signature
from .crypto_e2ee import E2EESession, encrypt_message_for_peer, decrypt_message_with_key
from .discovery import MeshDiscovery, PeerInfo
from .client import MeshClient
from .node import OpenClawMeshNode
from .bridge import SkillRegistry

from .network import (
    discover_nat_and_public_ip,
    NATProfile,
    WANRelayServer,
    WANRelayClient,
    KademliaDHT,
    Contact,
    RoutingTable,
)

from .engines import (
    detect_hardware,
    HardwareProfile,
    UniversalInferenceEngine,
    AutoModelManager,
    ModelRecommendation,
    DistributedMoEOrchestrator,
    MultiModalEngine,
)

__all__ = [
    "PROTOCOL_VERSION",
    "SERVICE_TYPE_JARVISMESH",
    "SERVICE_TYPE_OPENCLAW",
    "TaskRequest",
    "TaskChunk",
    "TaskResponse",
    "sign_request",
    "verify_request",
    "parse_message",
    "NodeIdentity",
    "TrustStore",
    "verify_ed25519_signature",
    "E2EESession",
    "encrypt_message_for_peer",
    "decrypt_message_with_key",
    "MeshDiscovery",
    "PeerInfo",
    "MeshClient",
    "OpenClawMeshNode",
    "SkillRegistry",
    "discover_nat_and_public_ip",
    "NATProfile",
    "WANRelayServer",
    "WANRelayClient",
    "KademliaDHT",
    "Contact",
    "RoutingTable",
    "detect_hardware",
    "HardwareProfile",
    "UniversalInferenceEngine",
    "AutoModelManager",
    "ModelRecommendation",
    "DistributedMoEOrchestrator",
    "MultiModalEngine",
]
