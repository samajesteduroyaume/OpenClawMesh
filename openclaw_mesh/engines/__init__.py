"""
Moteurs d'Inférence, Modèles, Parallélisme Distribué et Multi-Modal pour OpenClawMesh.
"""

from .distributed_cluster import (
    ClusterPipelineTopology,
    MultiMachineClusterOrchestrator,
    NodeLayerAllocation,
)
from .distributed_moe import DistributedMoEOrchestrator, PipelineStage
from .distributed_rag import (
    DistributedRAGEngine,
    LocalVectorIndex,
    VectorDocument,
    cosine_similarity,
)
from .distributed_vector_store import CRDTDistributedVectorStore
from .embeddings import UniversalEmbeddingEngine
from .extreme_quant import BitNetQuantizer, FP8Quantizer, QuantizationFormat, QuantizedTensor
from .federated_lora import FederatedLoRAOrchestrator, FederatedRoundReport, LoRAWeightDelta
from .hardware import HardwareProfile, detect_hardware
from .inference import UniversalInferenceEngine
from .kv_cache import SemanticKVCache
from .model_cache import CachedModelEntry, ModelCache
from .model_manager import AutoModelManager, ModelRecommendation
from .multimodal import MultiModalEngine
from .pipeline_parallelism import ActivationTensor, LayerBlock, LayerPipelineScheduler
from .speculative import (
    DistributedSpeculativeEngine,
    DraftCandidate,
    SpeculativeStats,
    VerificationResult,
)
from .video_stream import RealTimeVideoProcessor, VideoFrame, VideoStreamSummary
from .voice_pipeline import RealTimeVoicePipeline, VoiceStreamConfig

__all__ = [
    "detect_hardware",
    "HardwareProfile",
    "UniversalInferenceEngine",
    "UniversalEmbeddingEngine",
    "ModelCache",
    "CachedModelEntry",
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
    "MultiMachineClusterOrchestrator",
    "ClusterPipelineTopology",
    "NodeLayerAllocation",
    "RealTimeVoicePipeline",
    "VoiceStreamConfig",
    "CRDTDistributedVectorStore",
    "FederatedLoRAOrchestrator",
    "LoRAWeightDelta",
    "FederatedRoundReport",
    "RealTimeVideoProcessor",
    "VideoFrame",
    "VideoStreamSummary",
]
