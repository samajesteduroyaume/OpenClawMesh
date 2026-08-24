"""
Gestionnaire de Modèles & Quantification Automatique selon la VRAM pour OpenClawMesh.

Analyse la VRAM et le matériel disponible pour recommander et charger automatiquement
la meilleure version et quantification de modèle IA :
- Détection fine de la mémoire GPU/NPU et de la mémoire unifiée
- Sélection du format : GGUF (Q4_K_M, Q8_0), MLX (4-bit, 8-bit), PyTorch FP16/BF16
- Gestion du cache local (~/.cache/openclaw_mesh/models)
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

from .hardware import detect_hardware, HardwareProfile


@dataclass
class ModelRecommendation:
    model_name: str
    quantization: str  # "4bit", "8bit", "fp16", "bf16"
    format: str        # "mlx", "gguf", "safetensors", "openvino"
    estimated_vram_mb: float
    max_context_tokens: int
    recommended_batch_size: int
    description: str


class AutoModelManager:
    """Gestionnaire de modèles IA avec sélection et quantification dynamique."""

    def __init__(self, hardware: Optional[HardwareProfile] = None, cache_dir: Optional[Path] = None):
        self.hardware = hardware or detect_hardware()
        self.cache_dir = cache_dir or Path(os.path.expanduser("~/.cache/openclaw_mesh/models"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def recommend_best_model(self, task_type: str = "coding") -> ModelRecommendation:
        """Détermine le modèle et la quantification idéaux selon la mémoire disponible."""
        vram_mb = self.hardware.vram_total_mb
        backend = self.hardware.recommended_backend

        # Format de sortie selon l'accélérateur
        if backend == "mlx":
            fmt = "mlx"
        elif "openvino" in backend:
            fmt = "openvino"
        elif backend == "cuda":
            fmt = "safetensors"
        else:
            fmt = "gguf"

        # 1. Moins de 6 Go de VRAM (ou CPU standard)
        if vram_mb < 6000:
            return ModelRecommendation(
                model_name="Qwen2.5-Coder-1.5B-Instruct",
                quantization="4bit",
                format=fmt,
                estimated_vram_mb=1800.0,
                max_context_tokens=8192,
                recommended_batch_size=1,
                description="Ultra-léger & rapide, parfait pour CPU, iGPU ou petits GPUs.",
            )

        # 2. Entre 6 et 16 Go de VRAM (Configuration typique PC / Mac M-Series 16GB)
        elif 6000 <= vram_mb < 16000:
            return ModelRecommendation(
                model_name="Qwen2.5-Coder-7B-Instruct",
                quantization="4bit",
                format=fmt,
                estimated_vram_mb=5200.0,
                max_context_tokens=32768,
                recommended_batch_size=2,
                description="Équilibre parfait entre puissance de raisonnement, vitesse et compacité.",
            )

        # 3. Entre 16 et 32 Go de VRAM (GPU Pro / Mac M Pro/Max 32GB)
        elif 16000 <= vram_mb < 32000:
            return ModelRecommendation(
                model_name="Qwen2.5-Coder-14B-Instruct",
                quantization="8bit" if vram_mb < 24000 else "fp16",
                format=fmt,
                estimated_vram_mb=14500.0,
                max_context_tokens=65536,
                recommended_batch_size=4,
                description="Hautes performances pour tâches de code complexes et architectures logicielles.",
            )

        # 4. Plus de 32 Go de VRAM (Mac Studio 64GB/128GB, NVIDIA A100 / RTX 4090 Cluster)
        else:
            return ModelRecommendation(
                model_name="Qwen2.5-Coder-32B-Instruct",
                quantization="4bit" if vram_mb < 48000 else "fp16",
                format=fmt,
                estimated_vram_mb=28000.0,
                max_context_tokens=131072,
                recommended_batch_size=8,
                description="Modèle haut de gamme à niveau de précision maximal et raisonnement profond.",
            )

    def list_cached_models(self) -> list[dict[str, Any]]:
        """Liste les modèles présents dans le cache local."""
        models = []
        if self.cache_dir.exists():
            for item in self.cache_dir.iterdir():
                if item.is_dir():
                    size_mb = sum(f.stat().st_size for f in item.glob("**/*") if f.is_file()) / (1024 * 1024)
                    models.append({
                        "name": item.name,
                        "path": str(item),
                        "size_mb": round(size_mb, 2),
                    })
        return models
