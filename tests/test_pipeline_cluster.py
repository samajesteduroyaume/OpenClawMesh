"""Tests for Multi-Machine Distributed Cluster & Layer Sharding."""

import pytest

from openclaw_mesh.engines.distributed_cluster import MultiMachineClusterOrchestrator


@pytest.mark.asyncio
async def test_distributed_cluster_planning_and_forward():
    orchestrator = MultiMachineClusterOrchestrator("test-cluster")
    peers = [
        {
            "node_id": "mac-m3-node",
            "node_name": "Macbook M3 Max",
            "hardware_type": "apple_metal",
            "vram_mb": 64000,
        },
        {
            "node_id": "rtx4090-node",
            "node_name": "Desktop RTX 4090",
            "hardware_type": "nvidia_cuda",
            "vram_mb": 24000,
        },
        {
            "node_id": "npu-server",
            "node_name": "Intel Core Ultra Server",
            "hardware_type": "intel_npu",
            "vram_mb": 16000,
        },
    ]

    topology = orchestrator.plan_distribution(
        model_name="deepseek-v3-671b",
        total_layers=60,
        hidden_dim=4096,
        available_peers=peers,
    )

    assert topology.total_layers == 60
    assert len(topology.allocations) == 3
    assert topology.allocations[0].is_head is True
    assert topology.allocations[-1].is_tail is True
    assert sum(a.layer_count for a in topology.allocations) == 60

    # Execute forward activation pass simulation
    result = await orchestrator.execute_forward_pass(
        model_name="deepseek-v3-671b",
        prompt="Explain quantum gravity in one sentence",
    )
    assert result["model"] == "deepseek-v3-671b"
    assert result["nodes_participating"] == 3
    assert len(result["pipeline_stages"]) == 3
    assert result["tokens_generated"] > 0
