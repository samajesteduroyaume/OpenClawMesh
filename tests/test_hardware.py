import asyncio

import pytest

from openclaw_mesh.engines.hardware import HardwareProfile, detect_hardware
from openclaw_mesh.engines.inference import UniversalInferenceEngine


def test_hardware_detection():
    hw = detect_hardware()
    assert isinstance(hw, HardwareProfile)
    assert hw.os_name in ("Darwin", "Linux", "Windows")
    assert hw.cpu_cores_logical >= 1
    assert hw.cpu_model != ""
    assert hw.accelerator_name != ""
    assert hw.recommended_backend in (
        "mlx",
        "cuda",
        "rocm",
        "openvino",
        "openvino_npu",
        "openvino_gpu",
        "intel_cpu",
        "directml",
        "cpu",
    )

    d = hw.to_dict()
    assert "os_name" in d
    assert "accelerator_type" in d


def test_universal_inference_engine_sync():
    engine = UniversalInferenceEngine()
    status = engine.get_status()
    assert "accelerator" in status
    assert "recommended_backend" in status

    async def _run():
        with pytest.raises(RuntimeError, match="backend d'inférence réel"):
            await engine.generate(prompt="Test prompt", model="test", max_tokens=10)

    asyncio.run(_run())


def test_universal_inference_engine_stream():
    engine = UniversalInferenceEngine()

    async def _run():
        with pytest.raises(RuntimeError, match="backend de streaming réel"):
            async for _chunk in engine.generate_stream(prompt="Test streaming", model="test"):
                pass

    asyncio.run(_run())
