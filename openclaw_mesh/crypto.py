"""
Module de cryptographie asymétrique Ed25519 et gestion des identités OpenClawMesh.

100% compatible avec le système de sécurité JarvisMesh.
Gère les clés privées/publiques Ed25519, la signature, la vérification anti-rejeu,
et la liste blanche de confiance (TrustStore).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from .config import get_settings

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

_settings = get_settings()


def _signing_base_ed25519(
    request_id: str,
    origin: str,
    skill: str,
    ts: float,
    payload: dict[str, Any],
    pubkey_hex: str = "",
) -> bytes:
    """Génère la chaîne canonique d'octets à signer en Ed25519 (compatible JarvisMesh)."""
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    base = f"{request_id}|{origin}|{pubkey_hex}|{skill}|{ts!r}|{payload_json}"
    return base.encode("utf-8")


class NodeIdentity:
    """Représente l'identité cryptographique d'un nœud OpenClaw (Ed25519)."""

    def __init__(self, private_key: ed25519.Ed25519PrivateKey):
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

    def sign(
        self, request_id: str, origin: str, skill: str, ts: float, payload: dict[str, Any]
    ) -> str:
        """Signe canoniquement une requête TaskRequest en Ed25519."""
        data_to_sign = _signing_base_ed25519(
            request_id, origin, skill, ts, payload, self.public_key_hex
        )
        sig = self._private_key.sign(data_to_sign)
        return sig.hex()


def verify_ed25519_signature(
    public_key_hex: str,
    request_id: str,
    origin: str,
    skill: str,
    ts: float,
    payload: dict[str, Any],
    signature_hex: str,
    max_drift_seconds: float | None = None,
) -> bool:
    """
    Vérifie la signature Ed25519 d'une requête ainsi que l'horodatage anti-rejeu.
    """
    if not _HAS_CRYPTO:
        return False
    if not public_key_hex or not signature_hex:
        return False

    # Protection anti-rejeu par horodatage (tolérance +/- max_drift_seconds)
    drift_limit = max_drift_seconds or _settings.signature_max_drift_seconds
    now = time.time()
    if abs(now - ts) > drift_limit:
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

    def __init__(self, allowed_keys: set[str] | None = None, allow_all: bool = False):
        self.allowed_keys: set[str] = {k.lower() for k in (allowed_keys or set())}
        self.allow_all = allow_all

    def trust(self, pubkey_hex: str) -> None:
        if not isinstance(pubkey_hex, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", pubkey_hex):
            raise ValueError("Clé publique Ed25519 invalide")
        self.allowed_keys.add(pubkey_hex.lower())

    def revoke(self, pubkey_hex: str) -> None:
        self.allowed_keys.discard(pubkey_hex.lower())

    def is_trusted(self, pubkey_hex: str | None) -> bool:
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
            "allowed_keys": sorted(self.allowed_keys),
        }
        fd, temp_name = tempfile.mkstemp(prefix="truststore-", dir=file_path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as temp_file:
                temp_file.write(json.dumps(data, indent=2))
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_name, file_path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

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


def generate_self_signed_cert_and_key() -> tuple[bytes, bytes]:
    """Génère une paire certificat/clé privée TLS auto-signée à la volée."""
    if not _HAS_CRYPTO:
        raise ImportError("cryptography est requis pour générer un certificat TLS.")
    import datetime
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "openclaw-mesh-node")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def create_ephemeral_ssl_context() -> Any:
    """Crée un SSLContext serveur TLS auto-signé valide pour sécuriser instantanément les connexions WAN."""
    import ssl

    cert_pem, key_pem = generate_self_signed_cert_and_key()
    with (
        tempfile.NamedTemporaryFile("wb", delete=False) as c_file,
        tempfile.NamedTemporaryFile("wb", delete=False) as k_file,
    ):
        c_file.write(cert_pem)
        k_file.write(key_pem)
        c_path, k_path = c_file.name, k_file.name
    try:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(certfile=c_path, keyfile=k_path)
        return ctx
    finally:
        try:
            os.unlink(c_path)
            os.unlink(k_path)
        except OSError:
            pass
