"""
Chiffrement de Bout en Bout (E2EE) pour OpenClawMesh.

Garantit la confidentialité et l'intégrité absolue des messages échangés entre pairs,
même lorsqu'ils transitent par des serveurs relais WAN non sécurisés ou tiers :
- Échange de clés Diffie-Hellman sur courbe elliptique Curve25519 (X25519)
- Dérivation de clé HKDF-SHA256
- Chiffrement symétrique authentifié ChaCha20-Poly1305 (AEAD) avec nonces de 96 bits
"""
from __future__ import annotations
import json
import os
import time
from typing import Any, Optional, Union
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


class E2EESession:
    """Gère une session sécurisée chiffrée de bout en bout avec un pair distant."""

    def __init__(
        self,
        local_private_key: Optional[x25519.X25519PrivateKey] = None,
        peer_public_key_bytes: Optional[bytes] = None,
    ):
        self._private_key = local_private_key or x25519.X25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._shared_key: Optional[bytes] = None
        self._cipher: Optional[ChaCha20Poly1305] = None

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

    def establish_with_peer(self, peer_public_key_bytes: bytes, salt: bytes = b"openclaw_e2ee_salt_v1") -> None:
        """Calcule le secret partagé via ECDH X25519 et dérive la clé ChaCha20Poly1305."""
        if len(peer_public_key_bytes) != 32:
            raise ValueError(f"Taille de clé publique invalide (attendu 32 octets, reçu {len(peer_public_key_bytes)})")

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

    def encrypt(self, data: Union[str, bytes, dict, list], associated_data: Optional[bytes] = None) -> dict[str, Any]:
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

        nonce = os.urandom(12)  # Nonce de 96 bits
        ciphertext = self._cipher.encrypt(nonce, plaintext, associated_data)

        return {
            "version": "1.0",
            "algorithm": "ChaCha20-Poly1305",
            "ephemeral_pubkey": self.public_key_hex,
            "nonce": nonce.hex(),
            "ciphertext": ciphertext.hex(),
            "data_type": data_type,
            "timestamp": time.time(),
        }

    def decrypt(self, encrypted_package: dict[str, Any], associated_data: Optional[bytes] = None) -> Any:
        """Déchiffre un paquet chiffré ChaCha20-Poly1305."""
        if not self._cipher:
            # Si la session n'est pas encore initialisée, tenter d'utiliser la clé publique éphémère du paquet
            if "ephemeral_pubkey" in encrypted_package:
                peer_bytes = bytes.fromhex(encrypted_package["ephemeral_pubkey"])
                self.establish_with_peer(peer_bytes)
            else:
                raise RuntimeError("Session E2EE non établie et aucune clé éphémère trouvée dans le paquet.")

        nonce = bytes.fromhex(encrypted_package["nonce"])
        ciphertext = bytes.fromhex(encrypted_package["ciphertext"])
        data_type = encrypted_package.get("data_type", "json")

        plaintext = self._cipher.decrypt(nonce, ciphertext, associated_data)

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
    associated_data: Optional[bytes] = None,
) -> dict[str, Any]:
    """Chiffre un message unique destiné à un pair sans maintenir d'état."""
    session = E2EESession()
    peer_bytes = bytes.fromhex(peer_x25519_public_hex)
    session.establish_with_peer(peer_bytes)
    return session.encrypt(payload, associated_data=associated_data)


def decrypt_message_with_key(
    my_x25519_private_bytes: bytes,
    encrypted_package: dict[str, Any],
    associated_data: Optional[bytes] = None,
) -> Any:
    """Déchiffre un message reçu à l'aide de sa propre clé privée."""
    priv = x25519.X25519PrivateKey.from_private_bytes(my_x25519_private_bytes)
    session = E2EESession(local_private_key=priv)
    return session.decrypt(encrypted_package, associated_data=associated_data)
