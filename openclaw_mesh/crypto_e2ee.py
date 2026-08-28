"""
Chiffrement de Bout en Bout (E2EE) pour OpenClawMesh.

Garantit la confidentialité et l'intégrité absolue des messages échangés entre pairs,
même lorsqu'ils transitent par des serveurs relais WAN non sécurisés ou tiers :
- Échange de clés Diffie-Hellman sur courbe elliptique Curve25519 (X25519)
- Dérivation de clé HKDF-SHA256
- Chiffrement symétrique authentifié ChaCha20-Poly1305 (AEAD) avec nonces de 96 bits
- Protection anti-rejeu (replay) par horodatage + cache de nonces
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .config import get_settings

_settings = get_settings()
_DEFAULT_MAX_DRIFT = _settings.e2ee_max_drift_seconds
_CACHE_SIZE = _settings.e2ee_nonce_cache_size


def _e2ee_auth_base(package: dict[str, Any]) -> bytes:
    """Base canonique des métadonnées de session signées par l’identité du pair."""
    fields = {
        key: package[key]
        for key in (
            "version",
            "algorithm",
            "ephemeral_pubkey",
            "nonce",
            "ciphertext",
            "data_type",
            "timestamp",
        )
        if key in package
    }
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ReplayError(Exception):
    """Levée quand un paquet E2EE est rejeté par la protection anti-rejeu."""


class ReplayCache:
    """
    Cache glissé (sliding-window) des nonces déjà vus, avec éviction temporelle.

    Un nonce est rejeté comme rejeu tant qu'il n'a pas expiré de la fenêtre
    [maintenant - drift, maintenant + drift]. La taille est bornée : les entrées
    les plus anciennes sont évictées en FIFO lorsque la capacité est dépassée.
    """

    def __init__(self, max_size: int = _CACHE_SIZE):
        self._max_size = max_size
        # deque de (nonce: bytes, expiry: float)
        self._entries: deque[tuple[bytes, float]] = deque()
        # index accéléré nonce -> expiry
        self._index: dict[bytes, float] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._index)

    def _evict(self, now: float) -> None:
        """Retire les entrées expirées et, si nécessaire, les plus anciennes."""
        while self._entries and self._entries[0][1] <= now:
            nonce, _ = self._entries.popleft()
            self._index.pop(nonce, None)
        while len(self._entries) > self._max_size:
            nonce, _ = self._entries.popleft()
            self._index.pop(nonce, None)

    def has(self, nonce: bytes, now: float | None = None) -> bool:
        """Vrai si le nonce a déjà été vu et n'a pas expiré."""
        with self._lock:
            now = time.time() if now is None else now
            self._evict(now)
            return nonce in self._index

    def add(self, nonce: bytes, expiry: float) -> None:
        """Enregistre un nonce avec une date d'expiration donnée."""
        with self._lock:
            if nonce in self._index:
                return
            self._index[nonce] = expiry
            self._entries.append((nonce, expiry))
            self._evict(time.time())

    def check_and_add(self, nonce: bytes, expiry: float, now: float | None = None) -> bool:
        """Retourne vrai si le nonce est nouveau et l’enregistre atomiquement."""
        with self._lock:
            current = time.time() if now is None else now
            self._evict(current)
            if nonce in self._index:
                return False
            self._index[nonce] = expiry
            self._entries.append((nonce, expiry))
            self._evict(current)
            return True


class E2EESession:
    """Gère une session sécurisée chiffrée de bout en bout avec un pair distant."""

    def __init__(
        self,
        local_private_key: x25519.X25519PrivateKey | None = None,
        peer_public_key_bytes: bytes | None = None,
        max_drift_seconds: float | None = None,
        replay_cache: ReplayCache | None = None,
        enable_nonce_replay: bool = True,
        identity: Any | None = None,
        peer_identity_public_key: str | None = None,
        require_identity_binding: bool | None = None,
    ):
        self._private_key = local_private_key or x25519.X25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._shared_key: bytes | None = None
        self._cipher: ChaCha20Poly1305 | None = None

        self._max_drift_seconds = (
            max_drift_seconds if max_drift_seconds is not None else _DEFAULT_MAX_DRIFT
        )
        # Le cache de nonces anti-rejeu est activé par défaut. Un cache explicite peut
        # être fourni (partagé entre plusieurs sessions) ; sinon un cache privé est créé.
        # enable_nonce_replay=False désactive la vérification de nonces (stateless).
        if replay_cache is not None:
            self._replay_cache: ReplayCache | None = replay_cache
        elif enable_nonce_replay:
            self._replay_cache = ReplayCache()
        else:
            self._replay_cache = None
        # Historique des nonces localement produits pour éviter toute collision.
        self._sent_nonces: set[bytes] = set()
        self._identity = identity
        self._peer_identity_public_key = (
            peer_identity_public_key.lower() if peer_identity_public_key else None
        )
        self._require_identity_binding = (
            _settings.e2ee_require_identity_binding
            if require_identity_binding is None
            else require_identity_binding
        )
        if self._require_identity_binding and (
            self._identity is None or self._peer_identity_public_key is None
        ):
            raise ValueError(
                "Une identité locale et la clé d'identité attendue du pair sont requises en mode E2EE strict."
            )

        if peer_public_key_bytes:
            self.establish_with_peer(peer_public_key_bytes)

    @property
    def public_key_bytes(self) -> bytes:
        """Retourne la clé publique X25519 locale sous forme d'octets (32 bytes)."""
        return self._public_key.public_bytes_raw()

    @property
    def public_key_hex(self) -> str:
        """Retourne la clé publique X25519 locale sous forme hexadécimale."""
        return self.public_key_bytes.hex()

    @property
    def is_established(self) -> bool:
        """Indique si la clé partagée a été calculée avec le pair."""
        return self._cipher is not None

    def establish_with_peer(
        self, peer_public_key_bytes: bytes, salt: bytes = b"openclaw_e2ee_salt_v1"
    ) -> None:
        """Calcule le secret partagé via ECDH X25519 et dérive la clé ChaCha20Poly1305."""
        if len(peer_public_key_bytes) != 32:
            raise ValueError(
                f"Taille de clé publique invalide (attendu 32 octets, reçu {len(peer_public_key_bytes)})"
            )

        peer_pub = x25519.X25519PublicKey.from_public_bytes(peer_public_key_bytes)
        raw_shared_secret = self._private_key.exchange(peer_pub)

        # Dérivation cryptographique HKDF-SHA256
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"openclaw_mesh_e2ee_session_key",
        )
        self._shared_key = hkdf.derive(raw_shared_secret)
        self._cipher = ChaCha20Poly1305(self._shared_key)

    def _fresh_nonce(self) -> bytes:
        """Génère un nonce de 96 bits garanti non répété pour cette session."""
        for _ in range(64):
            nonce = os.urandom(12)
            if nonce not in self._sent_nonces:
                self._sent_nonces.add(nonce)
                return nonce
        # Très improbable : collision après 64 tentatives
        raise ReplayError("Échec de génération d'un nonce unique E2EE")

    def encrypt(
        self, data: str | bytes | dict[str, Any] | list[Any], associated_data: bytes | None = None
    ) -> dict[str, Any]:
        """Chiffre des données avec ChaCha20-Poly1305 et retourne le paquet chiffré."""
        if not self._cipher:
            raise RuntimeError("Session E2EE non établie : clé publique du pair requise.")

        if isinstance(data, (dict, list)):
            plaintext = json.dumps(data, separators=(",", ":")).encode("utf-8")
            data_type = "json"
        elif isinstance(data, str):
            plaintext = data.encode("utf-8")
            data_type = "text"
        elif isinstance(data, bytes):
            plaintext = data
            data_type = "bytes"
        else:
            raise TypeError(f"Type de données non pris en charge: {type(data)}")

        nonce = self._fresh_nonce()  # Nonce de 96 bits, unique par session
        ciphertext = self._cipher.encrypt(nonce, plaintext, associated_data)
        timestamp = time.time()
        package = {
            "version": "1.0",
            "algorithm": "ChaCha20-Poly1305",
            "ephemeral_pubkey": self.public_key_hex,
            "nonce": nonce.hex(),
            "ciphertext": ciphertext.hex(),
            "data_type": data_type,
            "timestamp": timestamp,
        }
        if self._identity is not None:
            auth_base = _e2ee_auth_base(package)
            package["identity_pubkey"] = self._identity.public_key_hex
            package["identity_signature"] = self._identity._private_key.sign(auth_base).hex()
        elif self._require_identity_binding:
            raise RuntimeError("Impossible de produire un paquet E2EE sans identité authentifiée")
        return package

    def decrypt(
        self,
        encrypted_package: dict[str, Any],
        associated_data: bytes | None = None,
        max_drift_seconds: float | None = None,
    ) -> Any:
        """
        Déchiffre un paquet chiffré ChaCha20-Poly1305 avec protection anti-rejeu.

        La protection combine une validation d'horodatage (tolérance +/- drift_limit)
        et un cache de nonces pour rejeter les rejets immédiats d'un paquet capturé.
        Le cache de nonces peut être désactivé à l'init de la session
        (enable_nonce_replay=False) pour un usage stateless.
        """
        if not self._cipher:
            if "ephemeral_pubkey" in encrypted_package:
                peer_bytes = bytes.fromhex(encrypted_package["ephemeral_pubkey"])
                self.establish_with_peer(peer_bytes)
            else:
                raise RuntimeError(
                    "Session E2EE non établie et aucune clé éphémère trouvée dans le paquet."
                )

        assert self._cipher is not None
        cipher = self._cipher
        drift_limit = (
            max_drift_seconds if max_drift_seconds is not None else self._max_drift_seconds
        )

        try:
            nonce = bytes.fromhex(encrypted_package["nonce"])
            ciphertext = bytes.fromhex(encrypted_package["ciphertext"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ReplayError("Paquet E2EE malformé") from exc
        if len(nonce) != 12 or len(ciphertext) < 16:
            raise ReplayError("Nonce ou ciphertext E2EE invalide")

        # 1. Protection anti-rejeu par horodatage (tolérance +/- drift_limit)
        ts = encrypted_package.get("timestamp")
        if not isinstance(ts, (int, float)):
            raise ReplayError("Horodatage E2EE absent ou invalide")
        if self._require_identity_binding and not self._peer_identity_public_key:
            raise ReplayError("Liaison d'identité E2EE obligatoire")
        if self._peer_identity_public_key:
            identity_hex = encrypted_package.get("identity_pubkey", "")
            signature_hex = encrypted_package.get("identity_signature", "")
            if identity_hex.lower() != self._peer_identity_public_key:
                raise ReplayError("Identité Ed25519 E2EE inattendue")
            try:
                identity_key = ed25519.Ed25519PublicKey.from_public_bytes(
                    bytes.fromhex(identity_hex)
                )
                identity_key.verify(
                    bytes.fromhex(signature_hex), _e2ee_auth_base(encrypted_package)
                )
            except (TypeError, ValueError, KeyError, InvalidSignature) as exc:
                raise ReplayError("Signature d'identité E2EE invalide") from exc
        now = time.time()
        if drift_limit > 0:
            if abs(now - ts) > drift_limit:
                raise ReplayError(
                    f"Paquet rejeté : horodatage hors tolérance (drift={abs(now - ts):.1f}s, limite={drift_limit}s)"
                )

        # 2. Protection anti-rejeu par nonce (détection de rejeu immédiat)
        cache = self._replay_cache
        if cache is not None:
            if cache.has(nonce, now):
                raise ReplayError("Paquet rejeté : nonce déjà vu (rejeu détecté)")

        data_type = encrypted_package.get("data_type", "json")

        # 3. Déchiffrement AEAD (lève InvalidTag en cas de torsion / mauvaise clé)
        plaintext = cipher.decrypt(nonce, ciphertext, associated_data)

        # 4. Enregistrement du nonce uniquement après un déchiffrement réussi
        if cache is not None:
            expiry = now + (drift_limit if drift_limit > 0 else _DEFAULT_MAX_DRIFT)
            if not cache.check_and_add(nonce, expiry, now):
                raise ReplayError("Paquet rejeté : nonce déjà vu (rejeu détecté)")

        if data_type == "json":
            return json.loads(plaintext.decode("utf-8"))
        elif data_type == "text":
            return plaintext.decode("utf-8")
        else:
            return plaintext


# ---------------------------------------------------------------------- #
# Fonctions d'Encapsulation Directe
# ---------------------------------------------------------------------- #
def encrypt_message_for_peer(
    peer_x25519_public_hex: str,
    payload: Any,
    associated_data: bytes | None = None,
) -> dict[str, Any]:
    """Chiffre un message unique destiné à un pair sans maintenir d'état."""
    session = E2EESession()
    peer_bytes = bytes.fromhex(peer_x25519_public_hex)
    session.establish_with_peer(peer_bytes)
    return session.encrypt(payload, associated_data=associated_data)


def decrypt_message_with_key(
    my_x25519_private_bytes: bytes,
    encrypted_package: dict[str, Any],
    associated_data: bytes | None = None,
    max_drift_seconds: float | None = None,
    replay_cache: ReplayCache | None = None,
) -> Any:
    """
    Déchiffre un message reçu à l'aide de sa propre clé privée.

    Contrairement à E2EESession.decrypt, il n'y a pas de session persistante :
    la protection anti-rejeu repose sur l'horodatage (max_drift_seconds) et sur
    un éventuel cache de nonces partagé fourni par l'appelant.
    """
    priv = x25519.X25519PrivateKey.from_private_bytes(my_x25519_private_bytes)
    enable_cache = replay_cache is not None
    session = E2EESession(
        local_private_key=priv,
        max_drift_seconds=max_drift_seconds,
        replay_cache=replay_cache,
        enable_nonce_replay=enable_cache,
    )
    return session.decrypt(
        encrypted_package,
        associated_data=associated_data,
        max_drift_seconds=max_drift_seconds,
    )
