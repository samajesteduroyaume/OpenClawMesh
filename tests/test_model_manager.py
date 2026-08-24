import pytest
from openclaw_mesh.engines.hardware import HardwareProfile
from openclaw_mesh.engines.model_manager import AutoModelManager, ModelRecommendation


def test_model_manager_recommendations_for_different_vrams():
    # 1. Petit profil (ex: CPU / 4GB VRAM)
    low_hw = HardwareProfile(
        os_name="Linux", os_version="6.0", architecture="x86_64",
        cpu_model="Intel Core i5", cpu_cores_logical=4, cpu_cores_physical=4,
        accelerator_type="cpu_generic", accelerator_name="Generic CPU",
        vram_total_mb=4000.0, recommended_backend="cpu"
    )
    mgr_low = AutoModelManager(hardware=low_hw)
    rec_low = mgr_low.recommend_best_model()
    assert rec_low.quantization == "4bit"
    assert "1.5B" in rec_low.model_name
    assert rec_low.format == "gguf"

    # 2. Profil Moyen (ex: Mac 16GB VRAM)
    mid_hw = HardwareProfile(
        os_name="Darwin", os_version="24.0", architecture="arm64",
        cpu_model="Apple M2", cpu_cores_logical=8, cpu_cores_physical=8,
        accelerator_type="apple_metal", accelerator_name="Apple Metal",
        vram_total_mb=16384.0, recommended_backend="mlx"
    )
    mgr_mid = AutoModelManager(hardware=mid_hw)
    rec_mid = mgr_mid.recommend_best_model()
    assert "14B" in rec_mid.model_name
    assert rec_mid.format == "mlx"

    # 3. Profil Haut de Gamme (ex: NVIDIA RTX 4090 / 64GB)
    high_hw = HardwareProfile(
        os_name="Linux", os_version="6.0", architecture="x86_64",
        cpu_model="AMD Ryzen 9", cpu_cores_logical=32, cpu_cores_physical=16,
        accelerator_type="nvidia_cuda", accelerator_name="NVIDIA RTX 4090",
        vram_total_mb=48000.0, recommended_backend="cuda"
    )
    mgr_high = AutoModelManager(hardware=high_hw)
    rec_high = mgr_high.recommend_best_model()
    assert "32B" in rec_high.model_name
    assert rec_high.format == "safetensors"
