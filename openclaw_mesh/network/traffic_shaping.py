"""OpenClawMesh Traffic Shaping, Anti-Analysis Padding & Multipath Onion Sharding.

Protects against network-level metadata analysis and timing inference attacks by enforcing
constant-size packet padding, randomized micro-jitter, and multi-circuit onion fragment sharding.
"""

from __future__ import annotations

import base64
import logging
import os
import random
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("openclaw_mesh.network.traffic_shaping")


@dataclass
class PaddedPacket:
    padded_payload_b64: str
    original_length: int
    target_bucket_size: int
    padding_bytes_added: int


class TrafficShaper:
    """Enforces constant-size padding and timing normalization to thwart traffic analysis."""

    STANDARD_BUCKET_SIZES = [256, 512, 1024, 2048, 4096, 8192]

    @classmethod
    def pad_payload(cls, data: bytes) -> PaddedPacket:
        """Pad a byte payload to the next standardized power-of-two bucket size."""
        orig_len = len(data)
        bucket_size = cls.STANDARD_BUCKET_SIZES[-1]
        for size in cls.STANDARD_BUCKET_SIZES:
            if orig_len + 4 <= size:
                bucket_size = size
                break

        # Format: 4-byte big-endian original length + data + random padding
        header = orig_len.to_bytes(4, byteorder="big")
        needed_padding = max(0, bucket_size - len(header) - orig_len)
        padding = os.urandom(needed_padding)
        padded_bytes = header + data + padding

        return PaddedPacket(
            padded_payload_b64=base64.b64encode(padded_bytes).decode("utf-8"),
            original_length=orig_len,
            target_bucket_size=bucket_size,
            padding_bytes_added=needed_padding,
        )

    @classmethod
    def unpad_payload(cls, padded_b64: str) -> bytes:
        """Strip padding and retrieve original payload bytes."""
        raw = base64.b64decode(padded_b64)
        if len(raw) < 4:
            raise ValueError("Invalid padded packet header")
        orig_len = int.from_bytes(raw[:4], byteorder="big")
        return raw[4 : 4 + orig_len]

    @staticmethod
    def calculate_micro_jitter(min_delay_ms: float = 1.0, max_delay_ms: float = 8.0) -> float:
        """Generate randomized micro-jitter delay in seconds to mask token inter-arrival intervals."""
        return random.uniform(min_delay_ms, max_delay_ms) / 1000.0


class MultipathOnionSharder:
    """Splits a payload into multiple interleaved shards dispatched across separate onion circuits."""

    @staticmethod
    def shard_payload(payload_bytes: bytes, num_shards: int = 2) -> list[dict[str, Any]]:
        """Split a byte payload into N interleaved shards."""
        shards: list[bytearray] = [bytearray() for _ in range(num_shards)]
        for i, byte in enumerate(payload_bytes):
            shards[i % num_shards].append(byte)

        return [
            {
                "shard_index": s_idx,
                "total_shards": num_shards,
                "data_b64": base64.b64encode(bytes(s)).decode("utf-8"),
            }
            for s_idx, s in enumerate(shards)
        ]

    @staticmethod
    def reassemble_shards(shard_dicts: list[dict[str, Any]]) -> bytes:
        """Reassemble interleaved shards back to original payload."""
        if not shard_dicts:
            return b""

        total_shards = shard_dicts[0]["total_shards"]
        sorted_shards = sorted(shard_dicts, key=lambda s: s["shard_index"])
        raw_shards = [base64.b64decode(s["data_b64"]) for s in sorted_shards]

        max_len = max(len(s) for s in raw_shards)
        reassembled = bytearray()

        for byte_pos in range(max_len):
            for s_idx in range(total_shards):
                if byte_pos < len(raw_shards[s_idx]):
                    reassembled.append(raw_shards[s_idx][byte_pos])

        return bytes(reassembled)
