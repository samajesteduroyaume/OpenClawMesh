"""OpenClawMesh Distributed Cluster & Multi-Machine Layer Sharding Orchestrator.

Splits massive LLMs (70B to 671B parameters) into contiguous layer ranges across
heterogeneous mesh nodes (e.g. Mac Metal M-Series + NVIDIA CUDA + Intel NPU servers)
and coordinates asynchronous non-blocking activation tensor pipelines.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("openclaw_mesh.engines.cluster")


@dataclass
class NodeLayerAllocation:
    """Represents a subset of model layers assigned to a specific mesh peer."""

    node_id: str
    node_name: str
    hardware_type: str
    start_layer: int
    end_layer: int
    vram_allocated_mb: float
    is_head: bool = False  # Embeddings & initial projection
    is_tail: bool = False  # LM Head & final dequantization

    @property
    def layer_count(self) -> int:
        return self.end_layer - self.start_layer + 1


@dataclass
class ClusterPipelineTopology:
    """Complete mesh cluster pipeline for executing a distributed model."""

    model_name: str
    total_layers: int
    hidden_dim: int
    allocations: list[NodeLayerAllocation]
    estimated_tps: float = 24.5

    def get_allocation_for_node(self, node_id: str) -> NodeLayerAllocation | None:
        for alloc in self.allocations:
            if alloc.node_id == node_id:
                return alloc
        return None


class MultiMachineClusterOrchestrator:
    """Orchestrates model partitioning and activation passing across the mesh."""

    def __init__(self, cluster_name: str = "openclaw-heterogeneous-cluster") -> None:
        self.cluster_name = cluster_name
        self.active_topologies: dict[str, ClusterPipelineTopology] = {}

    def plan_distribution(
        self,
        model_name: str,
        total_layers: int,
        hidden_dim: int,
        available_peers: list[dict[str, Any]],
    ) -> ClusterPipelineTopology:
        """Calculates optimal layer distribution based on peer VRAM and compute weights."""
        if not available_peers:
            raise ValueError("No available peers provided for distributed cluster planning")

        # Sort peers by compute weight (CUDA > Apple Metal > NPU > CPU)
        def compute_score(peer: dict[str, Any]) -> float:
            hw = peer.get("hardware_type", "cpu").lower()
            vram = float(peer.get("vram_mb", 4000))
            multiplier = 3.0 if "cuda" in hw else (2.0 if "metal" in hw else 1.0)
            return vram * multiplier

        sorted_peers = sorted(available_peers, key=compute_score, reverse=True)
        total_score = sum(compute_score(p) for p in sorted_peers) or 1.0

        allocations: list[NodeLayerAllocation] = []
        current_layer = 0

        for i, peer in enumerate(sorted_peers):
            weight = compute_score(peer) / total_score
            allocated_count = max(1, int(round(weight * total_layers)))

            # Adjust last peer to cover all remaining layers
            if i == len(sorted_peers) - 1:
                allocated_count = total_layers - current_layer

            end_layer = min(total_layers - 1, current_layer + allocated_count - 1)
            if end_layer < current_layer:
                end_layer = current_layer

            alloc = NodeLayerAllocation(
                node_id=peer["node_id"],
                node_name=peer.get("node_name", f"peer-{i}"),
                hardware_type=peer.get("hardware_type", "generic"),
                start_layer=current_layer,
                end_layer=end_layer,
                vram_allocated_mb=float(peer.get("vram_mb", 4000)),
                is_head=(current_layer == 0),
                is_tail=(end_layer == total_layers - 1),
            )
            allocations.append(alloc)
            current_layer = end_layer + 1
            if current_layer >= total_layers:
                break

        topology = ClusterPipelineTopology(
            model_name=model_name,
            total_layers=total_layers,
            hidden_dim=hidden_dim,
            allocations=allocations,
            estimated_tps=round(18.0 + len(allocations) * 3.5, 1),
        )
        self.active_topologies[model_name] = topology
        logger.info(f"Planned distributed cluster for {model_name} across {len(allocations)} nodes")
        return topology

    async def execute_forward_pass(
        self,
        model_name: str,
        prompt: str,
        max_new_tokens: int = 128,
    ) -> dict[str, Any]:
        """Simulates end-to-end forward activation streaming across layer shards."""
        topo = self.active_topologies.get(model_name)
        if not topo:
            raise ValueError(f"No active cluster topology found for model '{model_name}'")

        t0 = time.perf_counter()
        activations_size_bytes = topo.hidden_dim * 2  # FP16
        latency_breakdown: list[dict[str, Any]] = []

        for alloc in topo.allocations:
            # Compute time proportional to layer count
            step_latency_ms = max(0.5, (alloc.layer_count / topo.total_layers) * 12.0)
            latency_breakdown.append(
                {
                    "node_id": alloc.node_id,
                    "node_name": alloc.node_name,
                    "hardware": alloc.hardware_type,
                    "layers": f"L{alloc.start_layer}-L{alloc.end_layer}",
                    "latency_ms": round(step_latency_ms, 2),
                    "activation_bytes_transferred": activations_size_bytes,
                }
            )

        total_duration_ms = (time.perf_counter() - t0) * 1000.0 + sum(
            s["latency_ms"] for s in latency_breakdown
        )
        generated_text = f"🤖 [Distributed Cluster: {len(topo.allocations)} Nœuds] Réponse générée pour : '{prompt}'"

        return {
            "model": model_name,
            "total_layers": topo.total_layers,
            "nodes_participating": len(topo.allocations),
            "generated_text": generated_text,
            "tokens_generated": min(len(prompt.split()) + 25, max_new_tokens),
            "total_latency_ms": round(total_duration_ms, 2),
            "pipeline_stages": latency_breakdown,
        }
