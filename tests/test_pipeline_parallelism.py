import pytest

from openclaw_mesh.engines.pipeline_parallelism import (
    LayerPipelineScheduler,
)


@pytest.mark.asyncio
async def test_layer_pipeline_scheduler_chain():
    scheduler = LayerPipelineScheduler(total_model_layers=16)

    # Register discontinuous blocks
    scheduler.register_node_block("node-1", start_layer=0, end_layer=7, device_type="metal")
    scheduler.register_node_block("node-2", start_layer=8, end_layer=15, device_type="cuda")

    chain = scheduler.build_pipeline_chain()
    assert chain is not None
    assert len(chain) == 2
    assert chain[0].node_id == "node-1"
    assert chain[1].node_id == "node-2"

    # Forward activation
    input_tensor = LayerPipelineScheduler.pack_synthetic_activations([1, 128, 4096])
    out_tensor, latency = await scheduler.forward_pipeline_step(input_tensor, chain)

    assert out_tensor.layer_index == 15
    assert latency > 0.0


def test_incomplete_pipeline():
    scheduler = LayerPipelineScheduler(total_model_layers=32)
    scheduler.register_node_block("node-1", start_layer=0, end_layer=7)
    # Missing layers 8..31
    chain = scheduler.build_pipeline_chain()
    assert chain is None
