"""
Moteurs d'Inférence et Gestionnaires Matériels Multi-Plateformes pour OpenClawMesh.
"""
from .hardware import detect_hardware, HardwareProfile
from .inference import UniversalInferenceEngine

__all__ = ["detect_hardware", "HardwareProfile", "UniversalInferenceEngine"]
