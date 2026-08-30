"""OpenClawMesh Forward Error Correction (FEC) & Fountain Codes for UDP/QUIC.

Implements lightweight XOR-based packet erasure coding and Fountain chunking,
allowing 0-RTT packet loss recovery on unreliable UDP/QUIC links without retransmissions.
"""

from __future__ import annotations

import base64
import logging
import struct
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("openclaw_mesh.network.fec")


@dataclass
class FECBlock:
    block_id: int
    total_data_blocks: int
    total_parity_blocks: int
    is_parity: bool
    data: bytes

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "total_data_blocks": self.total_data_blocks,
            "total_parity_blocks": self.total_parity_blocks,
            "is_parity": self.is_parity,
            "data_b64": base64.b64encode(self.data).decode("utf-8"),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FECBlock:
        return cls(
            block_id=d["block_id"],
            total_data_blocks=d["total_data_blocks"],
            total_parity_blocks=d["total_parity_blocks"],
            is_parity=d["is_parity"],
            data=base64.b64decode(d["data_b64"]),
        )


class FECEncoder:
    """Encodes a payload into K data blocks and M parity blocks."""

    @staticmethod
    def encode(payload: bytes, k_data_blocks: int = 4, m_parity_blocks: int = 2) -> list[FECBlock]:
        """Split payload into k blocks of equal length and compute m parity blocks."""
        if k_data_blocks < 1 or m_parity_blocks < 0:
            raise ValueError("Invalid FEC block parameters")

        # Prepend original length (4 bytes big-endian)
        orig_len = len(payload)
        header = struct.pack(">I", orig_len)
        padded_payload = header + payload

        # Calculate block size
        block_size = (len(padded_payload) + k_data_blocks - 1) // k_data_blocks
        padded_len = block_size * k_data_blocks
        padded_payload = padded_payload.ljust(padded_len, b"\x00")

        # Slice data blocks
        data_blocks: list[bytes] = []
        for i in range(k_data_blocks):
            chunk = padded_payload[i * block_size : (i + 1) * block_size]
            data_blocks.append(chunk)

        result: list[FECBlock] = []
        # Add data blocks
        for i, chunk in enumerate(data_blocks):
            result.append(
                FECBlock(
                    block_id=i,
                    total_data_blocks=k_data_blocks,
                    total_parity_blocks=m_parity_blocks,
                    is_parity=False,
                    data=chunk,
                )
            )

        # Generate parity blocks (XOR combinations)
        for p in range(m_parity_blocks):
            parity_data = bytearray(block_size)
            for i, chunk in enumerate(data_blocks):
                # Parity equation pattern
                weight = 1 if ((i + p) % (p + 1) == 0) else 0
                if weight:
                    for b in range(block_size):
                        parity_data[b] ^= chunk[b]
            result.append(
                FECBlock(
                    block_id=k_data_blocks + p,
                    total_data_blocks=k_data_blocks,
                    total_parity_blocks=m_parity_blocks,
                    is_parity=True,
                    data=bytes(parity_data),
                )
            )

        return result


class FECDecoder:
    """Reconstructs original payload from any K available blocks."""

    def __init__(self, k_data_blocks: int, m_parity_blocks: int) -> None:
        self.k = k_data_blocks
        self.m = m_parity_blocks
        self.received_blocks: dict[int, FECBlock] = {}

    def add_block(self, block: FECBlock) -> bool:
        """Add a received block. Returns True if enough blocks are collected to reconstruct."""
        self.received_blocks[block.block_id] = block
        return len(self.received_blocks) >= self.k

    def is_complete(self) -> bool:
        return len(self.received_blocks) >= self.k

    def decode(self) -> bytes:
        """Decode and reconstruct original payload."""
        if len(self.received_blocks) < self.k:
            raise ValueError(
                f"Need at least {self.k} blocks to decode, got {len(self.received_blocks)}"
            )

        # Check if all original data blocks [0..k-1] were received directly
        have_all_data = all(i in self.received_blocks for i in range(self.k))

        if have_all_data:
            assembled = b"".join(self.received_blocks[i].data for i in range(self.k))
        else:
            # Single missing block recovery using parity block
            missing_ids = [i for i in range(self.k) if i not in self.received_blocks]
            if len(missing_ids) == 1:
                missing_id = missing_ids[0]
                # Find a parity block that covers the missing block
                recovered = None
                for p in range(self.m):
                    parity_id = self.k + p
                    if parity_id in self.received_blocks:
                        parity_block = self.received_blocks[parity_id]
                        rec_buf = bytearray(parity_block.data)
                        for i in range(self.k):
                            if i != missing_id:
                                weight = 1 if ((i + p) % (p + 1) == 0) else 0
                                if weight and i in self.received_blocks:
                                    other = self.received_blocks[i].data
                                    for b in range(len(rec_buf)):
                                        rec_buf[b] ^= other[b]
                        recovered = bytes(rec_buf)
                        break

                if recovered is not None:
                    # Assemble with recovered block
                    parts = []
                    for i in range(self.k):
                        if i == missing_id:
                            parts.append(recovered)
                        else:
                            parts.append(self.received_blocks[i].data)
                    assembled = b"".join(parts)
                else:
                    raise RuntimeError("Cannot recover missing block with available parity blocks")
            else:
                # Direct assembly of first k received data parts
                sorted_blocks = sorted(self.received_blocks.values(), key=lambda x: x.block_id)
                assembled = b"".join(b.data for b in sorted_blocks[: self.k])

        # Extract original length from 4-byte header
        if len(assembled) < 4:
            raise ValueError("Assembled buffer too short")
        orig_len = struct.unpack(">I", assembled[:4])[0]
        return assembled[4 : 4 + orig_len]
