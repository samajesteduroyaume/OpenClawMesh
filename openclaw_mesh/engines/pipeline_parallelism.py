"""OpenClawMesh Layer-by-Layer Pipeline Parallelism (Petals-Style Sharding).

Coordinates distributed transformer layer blocks partitioned across different mesh peers,
streaming intermediate activation tensors across nodes to run 70B-671B models collaboratively.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("openclaw_mesh.engines.pipeline_parallelism")


@dataclass
class LayerBlock:
    start_layer: int
    end_layer: int  # Inclusive
    node_id: str
    vram_allocated_mb: float
    device_type: str = "cuda"  # cuda, metal, rocm, cpu

    @property
    def num_layers(self) -> int:
        return (self.end_layer - self.start_layer) + 1


@dataclass
class ActivationTensor:
    shape: list[int]
    dtype: str  # fp16, bf16, fp32, int8
    data_b64: str
    layer_index: int
    sequence_id: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape": self.shape,
            "dtype": self.dtype,
            "data_b64": self.data_b64,
            "layer_index": self.layer_index,
            "sequence_id": self.sequence_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActivationTensor:
        return cls(
            shape=data["shape"],
            dtype=data["dtype"],
            data_b64=data["data_b64"],
            layer_index=data["layer_index"],
            sequence_id=data["sequence_id"],
            timestamp=data.get("timestamp", time.time()),
        )


class LayerPipelineScheduler:
    """Orchestrates pipeline chain across nodes for distributed inference."""

    def __init__(self, total_model_layers: int = 32) -> None:
        self.total_model_layers = total_model_layers
        self.registered_blocks: list[LayerBlock] = []

    def register_node_block(
        self,
        node_id: str,
        start_layer: int,
        end_layer: int,
        vram_mb: float = 4096.0,
        device_type: str = "cuda",
    ) -> None:
        """Register a node hosting a specific layer range."""
        block = LayerBlock(
            start_layer=start_layer,
            end_layer=end_layer,
            node_id=node_id,
            vram_allocated_mb=vram_mb,
            device_type=device_type,
        )
        self.registered_blocks.append(block)
        logger.info(
            f"Registered Pipeline Block: layers [{start_layer}..{end_layer}] on {node_id} ({device_type})"
        )

    def build_pipeline_chain(self) -> list[LayerBlock] | None:
        """Find an optimal contiguous chain covering [0..total_model_layers - 1]."""
        # Sort by start_layer
        sorted_blocks = sorted(self.registered_blocks, key=lambda b: b.start_layer)
        chain: list[LayerBlock] = []
        current_layer = 0

        for block in sorted_blocks:
            if block.start_layer <= current_layer <= block.end_layer:
                chain.append(block)
                current_layer = block.end_layer + 1
                if current_layer >= self.total_model_layers:
                    return chain

        if current_layer < self.total_model_layers:
            logger.warning(
                f"Incomplete pipeline: covers layers 0..{current_layer - 1} but requires {self.total_model_layers}"
            )
            return None
        return chain

    @staticmethod
    def pack_synthetic_activations(shape: list[int], dtype: str = "fp16") -> ActivationTensor:
        """Pack a synthetic zero-filled or dummy activation tensor for testing and transmission."""
        elem_count = 1
        for dim in shape:
            elem_count *= dim
        # 2 bytes per float16
        raw_bytes = struct.pack(f">{elem_count}e", *([0.1] * elem_count))
        return ActivationTensor(
            shape=shape,
            dtype=dtype,
            data_b64=base64.b64encode(raw_bytes).decode("utf-8"),
            layer_index=0,
            sequence_id="seq-test",
        )

    async def forward_pipeline_step(
        self,
        input_tensor: ActivationTensor,
        chain: list[LayerBlock],
    ) -> tuple[ActivationTensor, float]:
        """Simulate sequential pipeline pass across all nodes in the chain."""
        t0 = time.perf_counter()
        current_tensor = input_tensor

        for block in chain:
            logger.debug(
                f"Forwarding activations (layer {block.start_layer}..{block.end_layer}) -> Node {block.node_id}"
            )
            # Simulated network transmission & compute overhead
            await asyncio.sleep(0.005)  # 5ms network hop + layer compute
            current_tensor.layer_index = block.end_layer

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return current_tensor, elapsed_ms
