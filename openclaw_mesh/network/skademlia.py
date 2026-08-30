"""OpenClawMesh S/Kademlia Extension (Sybil & Eclipse Attack Resistance).

Implements static and dynamic cryptographic puzzles (Proof-of-Work) for node ID
generation and routing table acceptance, enforcing mathematical cost on Sybil adversaries.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import struct
import time
from dataclasses import dataclass

logger = logging.getLogger("openclaw_mesh.network.skademlia")

# Default difficulty parameters
DEFAULT_STATIC_DIFFICULTY = 12  # Leading zero bits required for Node ID creation
DEFAULT_DYNAMIC_DIFFICULTY = 8  # Leading zero bits for dynamic challenge response


@dataclass
class SKademliaIdentity:
    public_key: str  # Ed25519 or X25519 public key in hex/b64
    static_nonce: int  # Nonce solving the static crypto puzzle
    node_id_hex: str  # Generated 160-bit node ID (40 hex chars)
    created_at: float

    def to_dict(self) -> dict:
        return {
            "public_key": self.public_key,
            "static_nonce": self.static_nonce,
            "node_id_hex": self.node_id_hex,
            "created_at": self.created_at,
        }


def count_leading_zero_bits(hash_bytes: bytes) -> int:
    """Count the number of consecutive leading zero bits in a byte sequence."""
    total_zeros = 0
    for b in hash_bytes:
        if b == 0:
            total_zeros += 8
        else:
            # Count leading zeros in this single byte
            total_zeros += 8 - b.bit_length()
            break
    return total_zeros


class SKademliaPuzzleSolver:
    """Solves static and dynamic crypto-puzzles for S/Kademlia node validation."""

    @staticmethod
    def mine_static_puzzle(
        public_key: str,
        difficulty: int = DEFAULT_STATIC_DIFFICULTY,
        max_iterations: int = 10_000_000,
    ) -> tuple[int, str]:
        """Mine a static nonce for public_key that satisfies the static difficulty.

        Returns:
            (static_nonce, node_id_hex)
        """
        pub_bytes = public_key.encode("utf-8")
        nonce = secrets.randbits(32)
        start_time = time.time()

        for step in range(max_iterations):
            current_nonce = (nonce + step) & 0xFFFFFFFF
            payload = struct.pack(">I", current_nonce) + pub_bytes
            digest = hashlib.sha256(payload).digest()

            if count_leading_zero_bits(digest) >= difficulty:
                # 160-bit Node ID (first 20 bytes of sha1(digest) or sha256)
                node_id_bytes = hashlib.sha1(digest).digest()
                node_id_hex = node_id_bytes.hex()
                elapsed = time.time() - start_time
                logger.debug(
                    f"Mined S/Kademlia identity in {elapsed:.3f}s: nonce={current_nonce}, "
                    f"node_id={node_id_hex[:12]}..., difficulty={difficulty}"
                )
                return current_nonce, node_id_hex

        raise TimeoutError(f"Failed to solve static puzzle within {max_iterations} iterations")

    @staticmethod
    def verify_static_puzzle(
        public_key: str,
        static_nonce: int,
        node_id_hex: str,
        difficulty: int = DEFAULT_STATIC_DIFFICULTY,
    ) -> bool:
        """Verify that a node's static nonce and public key derive the declared node ID."""
        try:
            pub_bytes = public_key.encode("utf-8")
            payload = struct.pack(">I", static_nonce) + pub_bytes
            digest = hashlib.sha256(payload).digest()

            if count_leading_zero_bits(digest) < difficulty:
                return False

            expected_node_id = hashlib.sha1(digest).digest().hex()
            return expected_node_id.lower() == node_id_hex.lower()
        except Exception as e:
            logger.warning(f"Error validating static puzzle: {e}")
            return False

    @staticmethod
    def solve_dynamic_puzzle(
        node_id_hex: str,
        challenge: str,
        difficulty: int = DEFAULT_DYNAMIC_DIFFICULTY,
    ) -> int:
        """Solve an interactive dynamic puzzle for node authentication."""
        node_bytes = bytes.fromhex(node_id_hex)
        chal_bytes = challenge.encode("utf-8")
        nonce = 0

        while True:
            payload = node_bytes + chal_bytes + struct.pack(">I", nonce)
            digest = hashlib.sha256(payload).digest()
            if count_leading_zero_bits(digest) >= difficulty:
                return nonce
            nonce += 1
            if nonce > 50_000_000:
                raise TimeoutError("Dynamic puzzle solution exceeded maximum attempts")

    @staticmethod
    def verify_dynamic_puzzle(
        node_id_hex: str,
        challenge: str,
        nonce: int,
        difficulty: int = DEFAULT_DYNAMIC_DIFFICULTY,
    ) -> bool:
        """Verify dynamic challenge response."""
        try:
            node_bytes = bytes.fromhex(node_id_hex)
            chal_bytes = challenge.encode("utf-8")
            payload = node_bytes + chal_bytes + struct.pack(">I", nonce)
            digest = hashlib.sha256(payload).digest()
            return count_leading_zero_bits(digest) >= difficulty
        except Exception:
            return False


class SKademliaNodeValidator:
    """Validates peers before inserting into the Kademlia DHT routing table."""

    def __init__(
        self,
        static_difficulty: int = DEFAULT_STATIC_DIFFICULTY,
        dynamic_difficulty: int = DEFAULT_DYNAMIC_DIFFICULTY,
    ) -> None:
        self.static_difficulty = static_difficulty
        self.dynamic_difficulty = dynamic_difficulty
        self._verified_nodes: set[str] = set()

    def generate_challenge(self) -> str:
        return secrets.token_hex(16)

    def validate_peer_identity(
        self,
        node_id_hex: str,
        public_key: str,
        static_nonce: int,
    ) -> bool:
        """Check if peer satisfies static Sybil resistance requirement."""
        if node_id_hex in self._verified_nodes:
            return True

        valid = SKademliaPuzzleSolver.verify_static_puzzle(
            public_key=public_key,
            static_nonce=static_nonce,
            node_id_hex=node_id_hex,
            difficulty=self.static_difficulty,
        )
        if valid:
            self._verified_nodes.add(node_id_hex)
        return valid
