import asyncio
import pytest
from openclaw_mesh.engines.distributed_moe import DistributedMoEOrchestrator, PipelineStage


def test_distributed_moe_stage_splitting():
    nodes = ["mac-m1", "nvidia-gpu-1", "intel-ultra-node"]
    moe = DistributedMoEOrchestrator(cluster_nodes=nodes)

    assert len(moe.stages) == 3
    assert moe.stages[0].node_name == "mac-m1"
    assert moe.stages[0].layer_range == (0, 10)
    assert moe.stages[1].layer_range == (10, 20)
    assert moe.stages[2].layer_range == (20, 32)


def test_distributed_moe_pipeline_execution():
    moe = DistributedMoEOrchestrator(cluster_nodes=["node_a", "node_b"])

    async def _run():
        res = await moe.execute_distributed_pipeline("Test distributed MoE reasoning prompt")
        assert "result_text" in res
        assert "stages" in res
        assert len(res["stages"]) == 2
        assert res["total_duration_ms"] > 0

    asyncio.run(_run())
