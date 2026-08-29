"""
Moteurs d'Inférence, Modèles, Parallélisme Distribué et Multi-Modal pour OpenClawMesh.
"""

from .distributed_moe import DistributedMoEOrchestrator, PipelineStage
from .distributed_rag import (
    DistributedRAGEngine,
    LocalVectorIndex,
    VectorDocument,
    cosine_similarity,
)
from .extreme_quant import BitNetQuantizer, FP8Quantizer, QuantizationFormat, QuantizedTensor
from .hardware import HardwareProfile, detect_hardware
from .inference import UniversalInferenceEngine
from .kv_cache import SemanticKVCache
from .model_manager import AutoModelManager, ModelRecommendation
from .multimodal import MultiModalEngine
from .pipeline_parallelism import ActivationTensor, LayerBlock, LayerPipelineScheduler
from .speculative import (
    DistributedSpeculativeEngine,
    DraftCandidate,
    SpeculativeStats,
    VerificationResult,
)

__all__ = [
    "detect_hardware",
    "HardwareProfile",
    "UniversalInferenceEngine",
    "AutoModelManager",
    "ModelRecommendation",
    "DistributedMoEOrchestrator",
    "PipelineStage",
    "MultiModalEngine",
    "SemanticKVCache",
    "DistributedSpeculativeEngine",
    "DraftCandidate",
    "VerificationResult",
    "SpeculativeStats",
    "LayerPipelineScheduler",
    "LayerBlock",
    "ActivationTensor",
    "BitNetQuantizer",
    "FP8Quantizer",
    "QuantizationFormat",
    "QuantizedTensor",
    "DistributedRAGEngine",
    "LocalVectorIndex",
    "VectorDocument",
    "cosine_similarity",
]

