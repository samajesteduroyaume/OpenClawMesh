"""OpenClawMesh Multi-Hop Onion Routing (Tor-like Anonymity Circuit).

Implements layered cryptographic circuits where each relay node only sees
the immediate previous and next hops, completely obscuring the original sender
and intermediate network topology.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from openclaw_mesh.crypto_e2ee import (
    derive_shared_key,
    generate_ephemeral_keypair,
)

logger = logging.getLogger("openclaw_mesh.network.onion")


@dataclass
class OnionHop:
    node_id: str
    public_key_b64: str  # X25519 public key hex or b64
    endpoint: str | None = None


@dataclass
class OnionPacket:
    circuit_id: str
    ephemeral_public_key: str  # X25519 ephemeral pubkey for this hop
    payload: str  # Base64 encrypted layered payload
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "circuit_id": self.circuit_id,
            "ephemeral_public_key": self.ephemeral_public_key,
            "payload": self.payload,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OnionPacket:
        return cls(
            circuit_id=data["circuit_id"],
            ephemeral_public_key=data["ephemeral_public_key"],
            payload=data["payload"],
            created_at=data.get("created_at", time.time()),
        )


class OnionRouter:
    """Handles multi-hop onion encryption, circuit creation, and hop unwrapping."""

    def __init__(self, node_id: str, private_key_b64: str) -> None:
        self.node_id = node_id
        self.private_key_b64 = private_key_b64
        self._circuits: dict[str, list[OnionHop]] = {}

    def build_circuit(self, hops: list[OnionHop]) -> str:
        """Register a new circuit route."""
        circuit_id = uuid.uuid4().hex[:16]
        self._circuits[circuit_id] = hops
        logger.info(
            f"Built onion circuit [{circuit_id}] with {len(hops)} hops: {[h.node_id for h in hops]}"
        )
        return circuit_id

    def wrap_onion(
        self,
        circuit_id: str,
        destination_node_id: str,
        payload_data: dict[str, Any],
    ) -> OnionPacket:
        """Wrap a payload into successive cryptographic layers for each hop in reverse order."""
        hops = self._circuits.get(circuit_id)
        if not hops:
            raise ValueError(f"Circuit {circuit_id} not found")

        # Inner-most layer: Delivered to destination
        current_layer = {
            "action": "DELIVER",
            "destination": destination_node_id,
            "data": payload_data,
            "timestamp": time.time(),
        }
        current_bytes = json.dumps(current_layer).encode("utf-8")

        # Wrap in reverse (from last hop to first hop)
        first_ephemeral_pub: str | None = None
        next_hop_eph_pub: str | None = None

        for i in reversed(range(len(hops))):
            hop = hops[i]
            next_hop = hops[i + 1].node_id if i + 1 < len(hops) else destination_node_id

            eph_priv, eph_pub = generate_ephemeral_keypair()
            shared_key = derive_shared_key(eph_priv, hop.public_key_b64)

            # Format payload for this hop
            hop_instructions = {
                "next_hop": next_hop,
                "is_final": (i == len(hops) - 1),
                "next_ephemeral_pub": next_hop_eph_pub,
                "layer_bytes": base64.b64encode(current_bytes).decode("utf-8"),
            }
            hop_bytes = json.dumps(hop_instructions).encode("utf-8")

            # Encrypt with ChaCha20-Poly1305
            nonce = os.urandom(12)
            chacha = ChaCha20Poly1305(shared_key)
            encrypted_layer = chacha.encrypt(nonce, hop_bytes, None)

            # Pack nonce + ciphertext
            packed = nonce + encrypted_layer
            current_bytes = packed
            next_hop_eph_pub = eph_pub
            first_ephemeral_pub = eph_pub

        return OnionPacket(
            circuit_id=circuit_id,
            ephemeral_public_key=first_ephemeral_pub or "",
            payload=base64.b64encode(current_bytes).decode("utf-8"),
            created_at=time.time(),
        )

    def unwrap_hop(
        self,
        packet: OnionPacket,
    ) -> tuple[str, str | None, dict[str, Any] | None, OnionPacket | None]:
        """Unwrap one layer at the current hop.

        Returns:
            Tuple of (status, next_hop_id, delivered_payload, next_packet)
            - status: "FORWARD" or "DELIVERED"
            - next_hop_id: ID of the next peer (if FORWARD)
            - delivered_payload: Unpacked JSON if this is the destination
            - next_packet: Re-packaged onion packet for next hop
        """
        try:
            raw_packed = base64.b64decode(packet.payload)
            if len(raw_packed) < 28:
                raise ValueError("Corrupted onion packet length")

            nonce = raw_packed[:12]
            ciphertext = raw_packed[12:]

            shared_key = derive_shared_key(self.private_key_b64, packet.ephemeral_public_key)
            chacha = ChaCha20Poly1305(shared_key)
            decrypted_bytes = chacha.decrypt(nonce, ciphertext, None)

            hop_info = json.loads(decrypted_bytes.decode("utf-8"))
            next_hop = hop_info.get("next_hop")
            is_final = hop_info.get("is_final", False)
            next_eph_pub = hop_info.get("next_ephemeral_pub")
            layer_raw = base64.b64decode(hop_info.get("layer_bytes", ""))

            if is_final:
                # The inner layer is reached
                inner = json.loads(layer_raw.decode("utf-8"))
                return ("DELIVERED", None, inner.get("data"), None)
            else:
                # Forward to next hop with next hop's ephemeral public key
                next_pkt = OnionPacket(
                    circuit_id=packet.circuit_id,
                    ephemeral_public_key=next_eph_pub or "",
                    payload=base64.b64encode(layer_raw).decode("utf-8"),
                    created_at=time.time(),
                )
                return ("FORWARD", next_hop, None, next_pkt)

        except Exception as e:
            logger.error(f"Failed to unwrap onion hop on node {self.node_id}: {e}")
            raise
