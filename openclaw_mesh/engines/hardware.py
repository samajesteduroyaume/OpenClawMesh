"""
Détecteur Universel de Matériel & Accélérateurs IA pour OpenClawMesh.

Détecte et caractérise automatiquement :
- 🟢 NVIDIA CUDA GPUs (GeForce, RTX, A100, H100, etc.)
- 🔴 AMD GPUs (ROCm, HIP, Radeon, Instinct, DirectML)
- 🔵 Intel Core Ultra / Arc (Intel NPU, OpenVINO, oneAPI, iGPU Arc, AVX-512)
- 🟣 Apple Silicon (Metal GPU M1/M2/M3/M4 via MLX / Metal Performance Shaders)
- ⚪ CPU Universel (AVX2, AVX-512, ARM Neon)
"""

from __future__ import annotations

import importlib.util
import os
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any

from ..config import get_settings

_settings = get_settings()


@dataclass
class HardwareProfile:
    os_name: str
    os_version: str
    architecture: str
    cpu_model: str
    cpu_cores_logical: int
    cpu_cores_physical: int
    accelerator_type: (
        str  # "nvidia_cuda", "amd_rocm", "intel_openvino", "apple_metal", "cpu_generic"
    )
    accelerator_name: str
    vram_total_mb: float = 0.0
    vram_free_mb: float = 0.0
    has_cuda: bool = False
    has_rocm: bool = False
    has_intel_npu: bool = False
    has_intel_openvino: bool = False
    has_apple_metal: bool = False
    has_directml: bool = False
    detected_devices: list[dict[str, Any]] = field(default_factory=list)
    recommended_backend: str = "cpu"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get_cpu_name() -> str:
    """Récupère le nom précis du processeur selon l'OS."""
    system = platform.system()
    try:
        if system == "Darwin":
            cmd = ["sysctl", "-n", "machdep.cpu.brand_string"]
            return subprocess.check_output(cmd).decode().strip()
        elif system == "Linux":
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        elif system == "Windows":
            return platform.processor() or "Processeur Windows"
    except Exception:
        pass
    return platform.processor() or platform.machine()


def detect_hardware() -> HardwareProfile:
    """Analyse complète du matériel et sélection du meilleur moteur d'inférence."""
    sys_name = platform.system()
    arch = platform.machine()
    cpu_model = _get_cpu_name()
    logical_cores = os.cpu_count() or 1
    physical_cores = (
        max(1, logical_cores // 2)
        if "intel" in cpu_model.lower() or "amd" in cpu_model.lower()
        else logical_cores
    )

    devices = []
    has_cuda = False
    has_rocm = False
    has_intel_npu = False
    has_intel_openvino = False
    has_apple_metal = False
    has_directml = False

    acc_type = "cpu_generic"
    acc_name = f"CPU {cpu_model} ({logical_cores} threads)"
    total_vram = 0.0
    rec_backend = "cpu"

    # ------------------------------------------------------------------ #
    # 1. Détection NVIDIA CUDA
    # ------------------------------------------------------------------ #
    try:
        import torch

        if torch.cuda.is_available():
            has_cuda = True
            dev_count = torch.cuda.device_count()
            gpu_names = [torch.cuda.get_device_name(i) for i in range(dev_count)]
            acc_type = "nvidia_cuda"
            acc_name = f"NVIDIA CUDA: {', '.join(gpu_names)}"
            rec_backend = "cuda"

            for i in range(dev_count):
                props = torch.cuda.get_device_properties(i)
                vram_mb = props.total_memory / (1024 * 1024)
                total_vram += vram_mb
                devices.append(
                    {
                        "type": "nvidia_gpu",
                        "index": i,
                        "name": props.name,
                        "vram_mb": round(vram_mb, 2),
                        "compute_capability": f"{props.major}.{props.minor}",
                    }
                )
    except ImportError:
        # Fallback via nvidia-smi en ligne de commande
        try:
            out = (
                subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
            if out:
                has_cuda = True
                acc_type = "nvidia_cuda"
                acc_name = f"NVIDIA GPU (nvidia-smi): {out.splitlines()[0]}"
                rec_backend = "cuda"
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 2. Détection Apple Silicon Metal
    # ------------------------------------------------------------------ #
    if not has_cuda and sys_name == "Darwin" and "arm" in arch.lower():
        has_apple_metal = True
        acc_type = "apple_metal"
        acc_name = f"Apple Silicon Metal GPU ({cpu_model})"
        rec_backend = "mlx"

        # Mémoire unifiée Mac
        try:
            mem_bytes = int(
                subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode().strip()
            )
            total_vram = mem_bytes / (1024 * 1024)
        except Exception:
            total_vram = 16384.0  # 16 GB par défaut

        devices.append(
            {
                "type": "apple_metal",
                "name": cpu_model,
                "vram_unified_mb": round(total_vram, 2),
                "backend": "mlx / metal",
            }
        )

    # ------------------------------------------------------------------ #
    # 3. Détection AMD ROCm / DirectML
    # ------------------------------------------------------------------ #
    if not has_cuda and not has_apple_metal:
        if importlib.util.find_spec("torch_directml") is not None:
            has_directml = True
            acc_type = "amd_directml"
            acc_name = "AMD DirectML / Windows GPU"
            rec_backend = "directml"
            devices.append({"type": "directml", "name": "DirectML Device"})

        # Vérification ROCm
        if os.path.exists("/opt/rocm") or "rocm" in os.environ.get("HIP_PATH", "").lower():
            has_rocm = True
            acc_type = "amd_rocm"
            acc_name = "AMD ROCm GPU Acceleration"
            rec_backend = "rocm"

    # ------------------------------------------------------------------ #
    # 4. Détection Intel Core Ultra / NPU / OpenVINO
    # ------------------------------------------------------------------ #
    is_intel_ultra = "ultra" in cpu_model.lower() or "intel" in cpu_model.lower()
    try:
        import openvino as ov  # type: ignore

        has_intel_openvino = True
        core = ov.Core()
        ov_devices = core.available_devices
        if "NPU" in ov_devices:
            has_intel_npu = True
            acc_type = "intel_npu"
            acc_name = f"Intel Core Ultra NPU + OpenVINO ({cpu_model})"
            rec_backend = "openvino_npu"
        elif "GPU" in ov_devices:
            acc_type = "intel_gpu"
            acc_name = f"Intel Arc / iGPU + OpenVINO ({cpu_model})"
            rec_backend = "openvino_gpu"
        elif is_intel_ultra:
            acc_type = "intel_cpu_accelerated"
            acc_name = f"Intel Core Ultra (OpenVINO AMX/AVX) : {cpu_model}"
            rec_backend = "openvino"

        for d in ov_devices:
            devices.append(
                {
                    "type": f"intel_openvino_{d.lower()}",
                    "device": d,
                    "full_name": core.get_property(d, "FULL_DEVICE_NAME")
                    if hasattr(core, "get_property")
                    else d,
                }
            )
    except ImportError:
        if is_intel_ultra and acc_type == "cpu_generic":
            acc_name = f"Intel Core Ultra (Optimisé AVX2/AVX-512) : {cpu_model}"
            rec_backend = "intel_cpu"

    # Si aucun accélérateur spécifique n'a été sélectionné
    if acc_type == "cpu_generic":
        devices.append(
            {
                "type": "cpu",
                "name": cpu_model,
                "logical_cores": logical_cores,
                "architecture": arch,
            }
        )

    return HardwareProfile(
        os_name=sys_name,
        os_version=platform.version(),
        architecture=arch,
        cpu_model=cpu_model,
        cpu_cores_logical=logical_cores,
        cpu_cores_physical=physical_cores,
        accelerator_type=acc_type,
        accelerator_name=acc_name,
        vram_total_mb=round(total_vram, 2),
        has_cuda=has_cuda,
        has_rocm=has_rocm,
        has_intel_npu=has_intel_npu,
        has_intel_openvino=has_intel_openvino,
        has_apple_metal=has_apple_metal,
        has_directml=has_directml,
        detected_devices=devices,
        recommended_backend=rec_backend,
    )
