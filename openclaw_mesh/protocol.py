"""
Protocole OpenClawMesh — Messages échangés entre agents P2P.

100% compatible avec le format wire JarvisMesh 1.0.
Format JSON minimal, asynchrone, supportant le multiplexage, le streaming
de chunks et la double authentification HMAC-SHA256 et Ed25519.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

PROTOCOL_VERSION = "1.0"
SERVICE_TYPE_JARVISMESH = "_jarvismesh._tcp.local."
SERVICE_TYPE_OPENCLAW = "_openclawmesh._tcp.local."
SERVICE_TYPES = [SERVICE_TYPE_JARVISMESH, SERVICE_TYPE_OPENCLAW]

DESCRIBE_SKILL = "_describe_skills"
HEALTH_SKILL = "_health"
RESERVED_SKILLS = {DESCRIBE_SKILL, HEALTH_SKILL}


def _canonical_payload_json(payload: dict) -> str:
    """Sérialise le payload en JSON déterministe avec clés triées sans espaces."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _signing_base(request_id: str, origin: str, skill: str, ts: float, payload: dict) -> bytes:
    """Base canonique de signature HMAC-SHA256 compatible JarvisMesh."""
    payload_json = _canonical_payload_json(payload)
    base = f"{request_id}|{origin}|{skill}|{ts!r}|{payload_json}"
    return base.encode("utf-8")


def sign_request(psk: str, request_id: str, origin: str, skill: str, ts: float, payload: dict) -> str:
    """Calcule le HMAC-SHA256 hex d'une requête pour une clé pré-partagée."""
    mac = hmac.new(
        psk.encode("utf-8"),
        _signing_base(request_id, origin, skill, ts, payload),
        hashlib.sha256
    )
    return mac.hexdigest()


def verify_request(
    psk: str,
    request_id: str,
    origin: str,
    skill: str,
    ts: float,
    payload: dict,
    signature: Optional[str]
) -> bool:
    """Vérifie la signature HMAC-SHA256 d'une requête en temps constant."""
    if not signature:
        return False
    expected = sign_request(psk, request_id, origin, skill, ts, payload)
    return hmac.compare_digest(expected, signature)


@dataclass
class TaskRequest:
    """Requête d'exécution de compétence envoyée à un pair du maillage."""
    skill: str
    payload: dict = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    origin: str = ""
    ts: float = field(default_factory=time.time)
    type: str = "task_request"
    # Signature hex (HMAC-SHA256 ou Ed25519)
    sig: Optional[str] = None
    # Clé publique de l'émetteur (hex) si authentification Ed25519
    pubkey: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sign(self, psk: str) -> None:
        """Signe avec une clé partagée HMAC-SHA256."""
        self.sig = sign_request(psk, self.request_id, self.origin, self.skill, self.ts, self.payload)

    def verify(self, psk: str) -> bool:
        """Vérifie la signature HMAC-SHA256."""
        return verify_request(psk, self.request_id, self.origin, self.skill, self.ts, self.payload, self.sig)

    def sign_ed25519(self, identity: Any) -> None:
        """Signe avec une clé privée asymétrique Ed25519."""
        self.pubkey = identity.public_key_hex
        self.sig = identity.sign(self.request_id, self.origin, self.skill, self.ts, self.payload)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskRequest:
        return cls(
            skill=data.get("skill", ""),
            payload=data.get("payload", {}),
            request_id=data.get("request_id", ""),
            origin=data.get("origin", ""),
            ts=data.get("ts", 0.0),
            type=data.get("type", "task_request"),
            sig=data.get("sig"),
            pubkey=data.get("pubkey"),
        )


@dataclass
class TaskChunk:
    """Chunk intermédiaire pour le streaming token-par-token (ex: LLM)."""
    request_id: str
    index: int
    chunk: Any
    type: str = "task_chunk"

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskChunk:
        return cls(
            request_id=data.get("request_id", ""),
            index=data.get("index", 0),
            chunk=data.get("chunk"),
            type=data.get("type", "task_chunk"),
        )


@dataclass
class TaskResponse:
    """Réponse finale à une TaskRequest."""
    request_id: str
    ok: bool
    result: Any = None
    error: Optional[str] = None
    handled_by: str = ""
    streamed: bool = False
    type: str = "task_response"

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskResponse:
        return cls(
            request_id=data.get("request_id", ""),
            ok=data.get("ok", False),
            result=data.get("result"),
            error=data.get("error"),
            handled_by=data.get("handled_by", ""),
            streamed=data.get("streamed", False),
            type=data.get("type", "task_response"),
        )


def parse_message(raw: str) -> dict[str, Any]:
    """Parse une chaîne JSON en dictionnaire Python."""
    return json.loads(raw)
