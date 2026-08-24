"""
Moteurs d'Inférence, Modèles, Parallélisme Distribué et Multi-Modal pour OpenClawMesh.
"""
from .hardware import detect_hardware, HardwareProfile
from .inference import UniversalInferenceEngine
from .model_manager import AutoModelManager, ModelRecommendation
from .distributed_moe import DistributedMoEOrchestrator, PipelineStage
from .multimodal import MultiModalEngine

__all__ = [
    "detect_hardware",
    "HardwareProfile",
    "UniversalInferenceEngine",
    "AutoModelManager",
    "ModelRecommendation",
    "DistributedMoEOrchestrator",
    "PipelineStage",
    "MultiModalEngine",
]
