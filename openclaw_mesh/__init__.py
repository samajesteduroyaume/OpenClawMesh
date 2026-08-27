"""
OpenClawMesh — Protocole P2P & Skill Décentralisé pour OpenClaw.

100% compatible avec JarvisMesh 1.0.
Permet la découverte locale mDNS, le routage DHT Kademlia, la traversée NAT & Relais WAN,
le chiffrement de bout en bout (E2EE), la délégation multi-matériels (NVIDIA, AMD, Intel, Apple)
et l'inférence multi-modale (Vision, Whisper STT, TTS, MoE).
"""

__version__ = "1.1.0"

from .bridge import SkillRegistry
from .client import MeshClient
from .config import Settings, get_settings, reload_settings, reset_settings
from .crypto import NodeIdentity, TrustStore, verify_ed25519_signature
from .crypto_e2ee import E2EESession, decrypt_message_with_key, encrypt_message_for_peer
from .discovery import MeshDiscovery, PeerInfo
from .engines import (
    AutoModelManager,
    DistributedMoEOrchestrator,
    HardwareProfile,
    ModelRecommendation,
    MultiModalEngine,
    UniversalInferenceEngine,
    detect_hardware,
)
from .network import (
    Contact,
    KademliaDHT,
    NATProfile,
    RoutingTable,
    WANRelayClient,
    WANRelayServer,
    discover_nat_and_public_ip,
)
from .node import OpenClawMeshNode
from .protocol import (
    PROTOCOL_VERSION,
    SERVICE_TYPE_JARVISMESH,
    SERVICE_TYPE_OPENCLAW,
    TaskChunk,
    TaskRequest,
    TaskResponse,
    parse_message,
    sign_request,
    verify_request,
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
    "Settings",
    "get_settings",
    "reload_settings",
    "reset_settings",
]
