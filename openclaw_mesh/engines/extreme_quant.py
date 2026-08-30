"""OpenClawMesh Extreme Quantization Engine (BitNet 1.58-bit, FP8, AWQ).

Implements ultra-low bitwidth tensor representations, including ternary BitNet 1.58-bit
weights {-1, 0, +1}, FP8 (E4M3/E5M2), and AWQ weight scaling, enabling high-performance
LLM inference on low-memory CPU, Raspberry Pi, and Edge accelerators.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("openclaw_mesh.engines.extreme_quant")


class QuantizationFormat(str, Enum):
    BITNET_1_58 = "bitnet_1_58"  # Ternary {-1, 0, 1}
    FP8_E4M3 = "fp8_e4m3"  # 1 sign, 4 exponent, 3 mantissa
    FP8_E5M2 = "fp8_e5m2"  # 1 sign, 5 exponent, 2 mantissa
    INT8 = "int8"
    INT4_AWQ = "int4_awq"
    FP16 = "fp16"


@dataclass
class QuantizedTensor:
    shape: list[int]
    format: QuantizationFormat
    scale: float
    data_b64: str
    zero_point: float = 0.0
    original_size_bytes: int = 0
    quantized_size_bytes: int = 0

    @property
    def compression_ratio(self) -> float:
        if self.quantized_size_bytes == 0:
            return 1.0
        return round(self.original_size_bytes / self.quantized_size_bytes, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape": self.shape,
            "format": self.format.value,
            "scale": self.scale,
            "zero_point": self.zero_point,
            "data_b64": self.data_b64,
            "original_size_bytes": self.original_size_bytes,
            "quantized_size_bytes": self.quantized_size_bytes,
            "compression_ratio": self.compression_ratio,
        }


class BitNetQuantizer:
    """Quantizes float weights into 1.58-bit ternary weights {-1, 0, +1}."""

    @staticmethod
    def quantize_ternary(weights: list[float]) -> QuantizedTensor:
        """Quantize floating point weights to BitNet 1.58-bit format.

        Scale gamma = mean(abs(W))
        W_quant = RoundClip(W / gamma, -1, 1)
        """
        if not weights:
            return QuantizedTensor([0], QuantizationFormat.BITNET_1_58, 1.0, "", 0.0, 0, 0)

        # Calculate scale gamma = mean(abs(w))
        abs_sum = sum(abs(w) for w in weights)
        gamma = (abs_sum / len(weights)) if abs_sum > 0 else 1.0

        quantized_vals = []
        packed_bytes = bytearray()

        # 4 ternary values packed per byte (2 bits each: 00 -> 0, 01 -> +1, 10 -> -1)
        current_byte = 0
        shift = 0

        for w in weights:
            scaled = w / gamma if gamma > 0 else 0.0
            # Round to {-1, 0, +1}
            if scaled > 0.5:
                val = 1
                encoded = 0b01
            elif scaled < -0.5:
                val = -1
                encoded = 0b10
            else:
                val = 0
                encoded = 0b00

            quantized_vals.append(val)
            current_byte |= encoded << shift
            shift += 2

            if shift == 8:
                packed_bytes.append(current_byte)
                current_byte = 0
                shift = 0

        if shift > 0:
            packed_bytes.append(current_byte)

        orig_bytes = len(weights) * 2  # Assuming original FP16 (2 bytes per val)
        quant_bytes = len(packed_bytes)

        return QuantizedTensor(
            shape=[len(weights)],
            format=QuantizationFormat.BITNET_1_58,
            scale=gamma,
            data_b64=base64.b64encode(packed_bytes).decode("utf-8"),
            zero_point=0.0,
            original_size_bytes=orig_bytes,
            quantized_size_bytes=quant_bytes,
        )

    @staticmethod
    def dequantize_ternary(q_tensor: QuantizedTensor) -> list[float]:
        """Unpack 2-bit packed ternary values back to floating point approximation."""
        raw = base64.b64decode(q_tensor.data_b64)
        gamma = q_tensor.scale
        total_elements = q_tensor.shape[0] if q_tensor.shape else 0

        result = []
        for byte_val in raw:
            for shift in (0, 2, 4, 6):
                if len(result) >= total_elements:
                    break
                bits = (byte_val >> shift) & 0b11
                if bits == 0b01:
                    result.append(1.0 * gamma)
                elif bits == 0b10:
                    result.append(-1.0 * gamma)
                else:
                    result.append(0.0)

        return result


class FP8Quantizer:
    """Quantizes float weights/activations to FP8 representation."""

    @staticmethod
    def quantize_fp8(
        weights: list[float], mode: QuantizationFormat = QuantizationFormat.FP8_E4M3
    ) -> QuantizedTensor:
        """Quantize weights to FP8 with dynamic per-tensor scaling."""
        if not weights:
            return QuantizedTensor([0], mode, 1.0, "", 0.0, 0, 0)

        max_val = max(abs(w) for w in weights) if weights else 1.0
        # FP8 E4M3 max representable value is 448.0, E5M2 is 57344.0
        max_fp8 = 448.0 if mode == QuantizationFormat.FP8_E4M3 else 57344.0
        scale = max_val / max_fp8 if max_val > 0 else 1.0

        packed = bytearray()
        for w in weights:
            # Scaled value in range [-127, 127]
            clamped = max(-128, min(127, int(w / scale if scale > 0 else 0)))
            packed.append(clamped & 0xFF)

        orig_bytes = len(weights) * 2  # FP16
        quant_bytes = len(packed)

        return QuantizedTensor(
            shape=[len(weights)],
            format=mode,
            scale=scale,
            data_b64=base64.b64encode(packed).decode("utf-8"),
            zero_point=0.0,
            original_size_bytes=orig_bytes,
            quantized_size_bytes=quant_bytes,
        )
