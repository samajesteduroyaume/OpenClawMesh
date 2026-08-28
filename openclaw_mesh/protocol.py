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
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any

from .config import get_settings

_settings = get_settings()

PROTOCOL_VERSION = _settings.app_version
SERVICE_TYPE_JARVISMESH = "_jarvismesh._tcp.local."
SERVICE_TYPE_OPENCLAW = "_openclawmesh._tcp.local."
SERVICE_TYPES = _settings.mdns_service_types
_seen_hmac_requests: OrderedDict[tuple[str, str], float] = OrderedDict()
_HMAC_REPLAY_CACHE_SIZE = 10000

DESCRIBE_SKILL = "_describe_skills"
HEALTH_SKILL = "_health"
RESERVED_SKILLS = {DESCRIBE_SKILL, HEALTH_SKILL}


def _canonical_payload_json(payload: dict[str, Any]) -> str:
    """Sérialise le payload en JSON déterministe avec clés triées sans espaces."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _signing_base(
    request_id: str, origin: str, skill: str, ts: float, payload: dict[str, Any]
) -> bytes:
    """Base canonique de signature HMAC-SHA256 compatible JarvisMesh."""
    payload_json = _canonical_payload_json(payload)
    base = f"{request_id}|{origin}|{skill}|{ts!r}|{payload_json}"
    return base.encode("utf-8")


def sign_request(
    psk: str, request_id: str, origin: str, skill: str, ts: float, payload: dict[str, Any]
) -> str:
    """Calcule le HMAC-SHA256 hex d'une requête pour une clé pré-partagée."""
    mac = hmac.HMAC(
        psk.encode("utf-8"),
        _signing_base(request_id, origin, skill, ts, payload),
        digestmod=hashlib.sha256,
    )
    return mac.hexdigest()


def verify_request(
    psk: str,
    request_id: str,
    origin: str,
    skill: str,
    ts: float,
    payload: dict[str, Any],
    signature: str | None,
) -> bool:
    """Vérifie la signature HMAC-SHA256 d'une requête en temps constant."""
    if not signature or not request_id or not isinstance(ts, (int, float)):
        return False
    if abs(time.time() - float(ts)) > _settings.signature_max_drift_seconds:
        return False
    cache_key = (origin, request_id)
    if cache_key in _seen_hmac_requests:
        return False
    expected = sign_request(psk, request_id, origin, skill, ts, payload)
    valid = hmac.compare_digest(expected, signature)
    if valid:
        _seen_hmac_requests[cache_key] = time.time()
        _seen_hmac_requests.move_to_end(cache_key)
        while len(_seen_hmac_requests) > _HMAC_REPLAY_CACHE_SIZE:
            _seen_hmac_requests.popitem(last=False)
    return valid


@dataclass
class TaskRequest:
    """Requête d'exécution de compétence envoyée à un pair du maillage."""

    skill: str
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    origin: str = ""
    ts: float = field(default_factory=time.time)
    type: str = "task_request"
    # Signature hex (HMAC-SHA256 ou Ed25519)
    sig: str | None = None
    # Clé publique de l'émetteur (hex) si authentification Ed25519
    pubkey: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sign(self, psk: str) -> None:
        """Signe avec une clé partagée HMAC-SHA256."""
        self.sig = sign_request(
            psk, self.request_id, self.origin, self.skill, self.ts, self.payload
        )

    def verify(self, psk: str) -> bool:
        """Vérifie la signature HMAC-SHA256."""
        return verify_request(
            psk, self.request_id, self.origin, self.skill, self.ts, self.payload, self.sig
        )

    def sign_ed25519(self, identity: Any) -> None:
        """Signe avec une clé privée asymétrique Ed25519."""
        self.pubkey = identity.public_key_hex
        self.sig = identity.sign(self.request_id, self.origin, self.skill, self.ts, self.payload)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskRequest:
        if data.get("type") != "task_request":
            raise ValueError("Type de message TaskRequest invalide")
        if not isinstance(data.get("skill"), str) or not data["skill"]:
            raise ValueError("Skill invalide")
        if not isinstance(data.get("payload", {}), dict):
            raise ValueError("Payload invalide")
        if not isinstance(data.get("request_id"), str) or not data["request_id"]:
            raise ValueError("request_id invalide")
        if not isinstance(data.get("ts"), (int, float)):
            raise ValueError("Timestamp invalide")
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
    error: str | None = None
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
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Le message JSON doit être un objet")
    return data
