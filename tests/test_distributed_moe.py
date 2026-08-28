import asyncio

from openclaw_mesh.engines.distributed_moe import DistributedMoEOrchestrator


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


def test_quantized_tensor_buffer_serialization():
    from openclaw_mesh.engines.distributed_moe import QuantizedTensorBuffer

    # 1. Test float16 serialization
    values = [0.125, -0.5, 1.75, -2.0, 0.0]
    buf_f16 = QuantizedTensorBuffer.from_floats(values, shape=[1, 5], dtype="float16")
    assert buf_f16.data_b64 != ""
    recovered_f16 = buf_f16.to_floats()
    assert len(recovered_f16) == 5
    assert abs(recovered_f16[0] - 0.125) < 1e-3

    # 2. Test int8 quantization
    buf_int8 = QuantizedTensorBuffer.from_floats(values, shape=[1, 5], dtype="int8")
    assert buf_int8.dtype == "int8"
    recovered_int8 = buf_int8.to_floats()
    assert len(recovered_int8) == 5
    assert abs(recovered_int8[3] - (-2.0)) < 0.1
