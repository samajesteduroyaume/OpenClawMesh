"""
OpenClawMesh — Protocole P2P & Skill Décentralisé pour OpenClaw.

100% compatible avec JarvisMesh.
Permet la découverte locale mDNS, la délégation de tâches d'agents IA,
le streaming de tokens temps réel, et la communication chiffrée/signée.
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
from .discovery import MeshDiscovery, PeerInfo
from .client import MeshClient
from .node import OpenClawMeshNode
from .bridge import SkillRegistry

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
    "MeshDiscovery",
    "PeerInfo",
    "MeshClient",
    "OpenClawMeshNode",
    "SkillRegistry",
]
