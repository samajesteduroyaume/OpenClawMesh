"""
Module de cryptographie asymétrique Ed25519 et gestion des identités OpenClawMesh.

100% compatible avec le système de sécurité JarvisMesh.
Gère les clés privées/publiques Ed25519, la signature, la vérification anti-rejeu,
et la liste blanche de confiance (TrustStore).
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Optional, Set

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


def _signing_base_ed25519(
    request_id: str,
    origin: str,
    skill: str,
    ts: float,
    payload: dict,
    pubkey_hex: str = ""
) -> bytes:
    """Génère la chaîne canonique d'octets à signer en Ed25519 (compatible JarvisMesh)."""
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    base = f"{request_id}|{origin}|{pubkey_hex}|{skill}|{ts!r}|{payload_json}"
    return base.encode("utf-8")


class NodeIdentity:
    """Représente l'identité cryptographique d'un nœud OpenClaw (Ed25519)."""

    def __init__(self, private_key: "ed25519.Ed25519PrivateKey"):
        if not _HAS_CRYPTO:
            raise ImportError(
                "La bibliothèque 'cryptography' est requise pour l'identité Ed25519. "
                "Installez-la via `pip install cryptography`"
            )
        self._private_key = private_key
        self._public_key = private_key.public_key()
        self.public_key_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.public_key_hex = self.public_key_bytes.hex()
        self.node_id = self.public_key_hex[:16]

    @classmethod
    def generate(cls) -> NodeIdentity:
        """Génère une nouvelle paire de clés Ed25519 aléatoire."""
        if not _HAS_CRYPTO:
            raise ImportError("cryptography n'est pas installé.")
        key = ed25519.Ed25519PrivateKey.generate()
        return cls(key)

    @classmethod
    def from_private_bytes(cls, raw_bytes: bytes) -> NodeIdentity:
        """Charge une identité depuis 32 octets de clé privée brute."""
        if not _HAS_CRYPTO:
            raise ImportError("cryptography n'est pas installé.")
        key = ed25519.Ed25519PrivateKey.from_private_bytes(raw_bytes)
        return cls(key)

    @classmethod
    def from_private_hex(cls, hex_str: str) -> NodeIdentity:
        """Charge une identité depuis une chaîne hexadécimale de 64 caractères."""
        return cls.from_private_bytes(bytes.fromhex(hex_str.strip()))

    def save(self, path: str | Path) -> None:
        """Enregistre la clé privée sur disque avec permissions strictes (0600)."""
        file_path = Path(path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        raw_private = self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        file_path.write_bytes(raw_private)
        try:
            os.chmod(file_path, 0o600)
        except Exception:
            pass

    @classmethod
    def load(cls, path: str | Path) -> NodeIdentity:
        """Charge une clé privée depuis un fichier sur disque."""
        file_path = Path(path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Fichier d'identité introuvable : {file_path}")
        raw = file_path.read_bytes()
        return cls.from_private_bytes(raw)

    def sign(self, request_id: str, origin: str, skill: str, ts: float, payload: dict) -> str:
        """Signe canoniquement une requête TaskRequest en Ed25519."""
        data_to_sign = _signing_base_ed25519(request_id, origin, skill, ts, payload, self.public_key_hex)
        sig = self._private_key.sign(data_to_sign)
        return sig.hex()


def verify_ed25519_signature(
    public_key_hex: str,
    request_id: str,
    origin: str,
    skill: str,
    ts: float,
    payload: dict,
    signature_hex: str,
    max_drift_seconds: float = 300.0,
) -> bool:
    """
    Vérifie la signature Ed25519 d'une requête ainsi que l'horodatage anti-rejeu.
    """
    if not _HAS_CRYPTO:
        return False
    if not public_key_hex or not signature_hex:
        return False

    # Protection anti-rejeu par horodatage (tolérance +/- max_drift_seconds)
    now = time.time()
    if abs(now - ts) > max_drift_seconds:
        return False

    try:
        pub_bytes = bytes.fromhex(public_key_hex)
        sig_bytes = bytes.fromhex(signature_hex)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
        data = _signing_base_ed25519(request_id, origin, skill, ts, payload, public_key_hex)
        public_key.verify(sig_bytes, data)
        return True
    except Exception:
        return False


class TrustStore:
    """Gestionnaire de confiance des clés publiques pour OpenClawMesh."""

    def __init__(self, allowed_keys: Optional[Set[str]] = None, allow_all: bool = False):
        self.allowed_keys: Set[str] = {k.lower() for k in (allowed_keys or set())}
        self.allow_all = allow_all

    def trust(self, pubkey_hex: str) -> None:
        self.allowed_keys.add(pubkey_hex.lower())

    def revoke(self, pubkey_hex: str) -> None:
        self.allowed_keys.discard(pubkey_hex.lower())

    def is_trusted(self, pubkey_hex: Optional[str]) -> bool:
        if self.allow_all:
            return True
        if not pubkey_hex:
            return False
        return pubkey_hex.lower() in self.allowed_keys

    def save(self, path: str | Path) -> None:
        file_path = Path(path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "allow_all": self.allow_all,
            "allowed_keys": sorted(list(self.allowed_keys)),
        }
        file_path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> TrustStore:
        file_path = Path(path).resolve()
        if not file_path.is_file():
            return cls()
        try:
            data = json.loads(file_path.read_text())
            return cls(
                allowed_keys=set(data.get("allowed_keys", [])),
                allow_all=data.get("allow_all", False),
            )
        except Exception:
            return cls()
