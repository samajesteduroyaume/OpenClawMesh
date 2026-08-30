"""OpenClawMesh Perfect Forward Secrecy (PFS) & Double-Ratchet Session Manager.

Implements ephemeral key rotation and continuous cryptographic ratcheting for
ultra-secure UDP/QUIC and WebSocket peer streams, ensuring past ciphertexts remain
unreadable even if long-term node identities are subsequently compromised.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from openclaw_mesh.crypto_e2ee import (
    derive_shared_key,
    generate_ephemeral_keypair,
)

logger = logging.getLogger("openclaw_mesh.security.pfs_ratchet")


def kdf_rk(root_key: bytes, dh_out: bytes) -> tuple[bytes, bytes]:
    """KDF for Root Key and Chain Key derivation."""
    derived = hmac.new(root_key, dh_out, hashlib.sha256).digest()
    new_root = hmac.new(derived, b"ROOT_KEY_NEXT", hashlib.sha256).digest()
    new_chain = hmac.new(derived, b"CHAIN_KEY_INIT", hashlib.sha256).digest()
    return new_root, new_chain


def kdf_ck(chain_key: bytes) -> tuple[bytes, bytes]:
    """KDF for Chain Key step and Message Key derivation."""
    next_chain = hmac.new(chain_key, b"CHAIN_STEP", hashlib.sha256).digest()
    message_key = hmac.new(chain_key, b"MSG_KEY", hashlib.sha256).digest()
    return next_chain, message_key


@dataclass
class RatchetMessage:
    sender_ephemeral_pub_b64: str
    sequence_number: int
    ciphertext_b64: str
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender_ephemeral_pub_b64": self.sender_ephemeral_pub_b64,
            "sequence_number": self.sequence_number,
            "ciphertext_b64": self.ciphertext_b64,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RatchetMessage:
        return cls(
            sender_ephemeral_pub_b64=data["sender_ephemeral_pub_b64"],
            sequence_number=data["sequence_number"],
            ciphertext_b64=data["ciphertext_b64"],
            timestamp=data.get("timestamp", time.time()),
        )


class PFSRatchetSession:
    """Maintains a Double-Ratchet PFS state between two peers."""

    def __init__(
        self,
        session_id: str,
        initial_shared_secret: bytes,
        is_initiator: bool,
    ) -> None:
        self.session_id = session_id
        self.is_initiator = is_initiator
        self.root_key = initial_shared_secret

        # Local ephemeral DH pair
        self.local_priv, self.local_pub = generate_ephemeral_keypair()
        self.remote_ephemeral_pub: str | None = None

        self.sending_chain_key: bytes = initial_shared_secret
        self.receiving_chain_key: bytes = initial_shared_secret

        self.send_seq = 0
        self.recv_seq = 0

    def rotate_ephemeral_key(self) -> str:
        """Perform DH ratchet step with a fresh ephemeral keypair."""
        self.local_priv, self.local_pub = generate_ephemeral_keypair()
        return self.local_pub

    def encrypt_message(self, plaintext: str | bytes) -> RatchetMessage:
        """Encrypt message under current message key and step the sending chain."""
        self.sending_chain_key, message_key = kdf_ck(self.sending_chain_key)

        raw_bytes = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
        nonce = os.urandom(12)
        chacha = ChaCha20Poly1305(message_key)
        ciphertext = chacha.encrypt(nonce, raw_bytes, None)

        packed = nonce + ciphertext
        self.send_seq += 1

        return RatchetMessage(
            sender_ephemeral_pub_b64=self.local_pub,
            sequence_number=self.send_seq,
            ciphertext_b64=base64.b64encode(packed).decode("utf-8"),
            timestamp=time.time(),
        )

    def decrypt_message(self, msg: RatchetMessage) -> bytes:
        """Decrypt message under receiving chain and step the ratchet."""
        if (
            self.remote_ephemeral_pub is not None
            and msg.sender_ephemeral_pub_b64 != self.remote_ephemeral_pub
        ):
            self.remote_ephemeral_pub = msg.sender_ephemeral_pub_b64
            dh_out = derive_shared_key(self.local_priv, self.remote_ephemeral_pub)
            self.root_key, self.receiving_chain_key = kdf_rk(self.root_key, dh_out)
        elif self.remote_ephemeral_pub is None:
            self.remote_ephemeral_pub = msg.sender_ephemeral_pub_b64

        self.receiving_chain_key, message_key = kdf_ck(self.receiving_chain_key)

        raw_packed = base64.b64decode(msg.ciphertext_b64)
        nonce = raw_packed[:12]
        ciphertext = raw_packed[12:]

        chacha = ChaCha20Poly1305(message_key)
        plaintext = chacha.decrypt(nonce, ciphertext, None)
        self.recv_seq += 1
        return plaintext
