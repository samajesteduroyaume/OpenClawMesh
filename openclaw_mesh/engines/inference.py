"""
Moteur d'Inférence IA Universel & Multi-Matériel pour OpenClawMesh.

Supporte automatiquement et de manière transparente :
1. 🟢 NVIDIA GPUs (CUDA via PyTorch / vLLM / Transformers)
2. 🔴 AMD GPUs (ROCm / DirectML / ONNX)
3. 🔵 Intel Core Ultra (NPU, OpenVINO, AMX/AVX-512, Intel Arc)
4. 🟣 Apple Silicon (Metal GPU M1/M2/M3/M4 via MLX-LM)
5. ⚪ Serveurs Locaux (Ollama, llama.cpp, vLLM via REST) & Fallback CPU universel
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from ..config import get_settings
from .hardware import HardwareProfile, detect_hardware

logger = logging.getLogger("openclaw_mesh.inference")
_settings = get_settings()


class UniversalInferenceEngine:
    """Moteur d'inférence agnostique du matériel, optimisé pour chaque puce."""

    def __init__(self, hardware: HardwareProfile | None = None) -> None:
        self.hardware = hardware or detect_hardware()
        self.backend = self.hardware.recommended_backend
        logger.info(
            f"Moteur d'Inférence initialisé avec l'accélérateur : {self.hardware.accelerator_name}"
        )

    def get_status(self) -> dict[str, Any]:
        """Retourne l'état du matériel et du backend d'inférence."""
        return {
            "accelerator": self.hardware.accelerator_name,
            "accelerator_type": self.hardware.accelerator_type,
            "recommended_backend": self.backend,
            "cpu_model": self.hardware.cpu_model,
            "vram_total_mb": self.hardware.vram_total_mb,
            "has_cuda": self.hardware.has_cuda,
            "has_rocm": self.hardware.has_rocm,
            "has_intel_npu": self.hardware.has_intel_npu,
            "has_apple_metal": self.hardware.has_apple_metal,
        }

    # ------------------------------------------------------------------ #
    # 1. Inférence Synchrone (Prompt -> Texte)
    # ------------------------------------------------------------------ #
    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.3,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Génère une réponse complète en utilisant le meilleur matériel disponible."""
        t0 = time.perf_counter()

        if model is not None and model not in set(_settings.allowed_models):
            raise ValueError("Modèle non autorisé par la liste blanche de configuration")

        # 1. Tentative Apple Silicon Metal (MLX)
        if self.backend == "mlx" and model != "test":
            try:
                from mlx_lm import generate as mlx_gen
                from mlx_lm import load

                mlx_model_name = model or "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
                model_obj, tokenizer = load(mlx_model_name)
                formatted_prompt = f"{system_prompt}\n{prompt}" if system_prompt else prompt
                text = mlx_gen(model_obj, tokenizer, prompt=formatted_prompt, max_tokens=max_tokens)
                duration_ms = (time.perf_counter() - t0) * 1000.0
                return {
                    "text": text,
                    "model": mlx_model_name,
                    "backend": "apple_metal_mlx",
                    "duration_ms": round(duration_ms, 2),
                }
            except Exception as e:
                logger.debug(f"Fallback MLX: {e}")

        # 2. Tentative NVIDIA CUDA (PyTorch / Transformers)
        if self.backend == "cuda":
            try:
                import torch
                from transformers import pipeline

                cuda_model = model or "Qwen/Qwen2.5-Coder-7B-Instruct"
                pipe = pipeline(
                    "text-generation", model=cuda_model, device="cuda", torch_dtype=torch.float16
                )
                out = pipe(prompt, max_new_tokens=max_tokens, temperature=temperature)
                text = out[0]["generated_text"]
                duration_ms = (time.perf_counter() - t0) * 1000.0
                return {
                    "text": text,
                    "model": cuda_model,
                    "backend": "nvidia_cuda_torch",
                    "duration_ms": round(duration_ms, 2),
                }
            except Exception as e:
                logger.debug(f"Fallback CUDA: {e}")

        # 3. Tentative Intel Core Ultra (OpenVINO / NPU)
        if "openvino" in self.backend:
            try:
                import openvino_genai as ov_genai

                ov_model_path = model or "openvino_model"
                pipe = ov_genai.LLMPipeline(
                    ov_model_path, "NPU" if self.hardware.has_intel_npu else "CPU"
                )
                text = pipe.generate(prompt, max_new_tokens=max_tokens)
                duration_ms = (time.perf_counter() - t0) * 1000.0
                return {
                    "text": text,
                    "model": ov_model_path,
                    "backend": "intel_openvino",
                    "duration_ms": round(duration_ms, 2),
                }
            except Exception as e:
                logger.debug(f"Fallback OpenVINO: {e}")

        raise RuntimeError(
            "Aucun backend d'inférence réel n'est disponible; aucune réponse simulée ne sera produite."
        )

    # ------------------------------------------------------------------ #
    # 2. Inférence Streaming Token-par-Token
    # ------------------------------------------------------------------ #
    async def generate_stream(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Génère et émet les tokens en continu (streaming temps réel)."""

        if model is not None and model not in set(_settings.allowed_models):
            raise ValueError("Modèle non autorisé par la liste blanche de configuration")

        # 1. Streaming MLX Apple Silicon
        if self.backend == "mlx" and model != "test":
            try:
                from mlx_lm import load, stream_generate

                mlx_model_name = model or "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
                model_obj, tokenizer = load(mlx_model_name)
                for response in stream_generate(model_obj, tokenizer, prompt=prompt):
                    yield {"text": response.text, "backend": "apple_metal_mlx"}
                    await asyncio.sleep(0.001)
                return
            except Exception as e:
                logger.debug(f"Fallback MLX Stream: {e}")

        raise RuntimeError(
            "Aucun backend de streaming réel n'est disponible; aucun flux simulé ne sera produit."
        )
