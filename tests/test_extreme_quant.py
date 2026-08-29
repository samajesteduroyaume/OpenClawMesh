from openclaw_mesh.engines.extreme_quant import (
    BitNetQuantizer,
    FP8Quantizer,
    QuantizationFormat,
)


def test_bitnet_ternary_quantize_dequantize():
    weights = [0.8, -0.7, 0.05, -0.02, 1.2, -1.1, 0.4, -0.3]
    q_tensor = BitNetQuantizer.quantize_ternary(weights)

    assert q_tensor.format == QuantizationFormat.BITNET_1_58
    assert q_tensor.quantized_size_bytes < q_tensor.original_size_bytes
    assert q_tensor.compression_ratio > 1.0

    dequant = BitNetQuantizer.dequantize_ternary(q_tensor)
    assert len(dequant) == len(weights)
    # Check that dequantized values are in {-gamma, 0, +gamma}
    gamma = q_tensor.scale
    for val in dequant:
        assert round(val, 4) in (round(gamma, 4), round(-gamma, 4), 0.0)


def test_fp8_quantize():
    weights = [0.5, -0.5, 12.0, -10.0]
    q_tensor = FP8Quantizer.quantize_fp8(weights, mode=QuantizationFormat.FP8_E4M3)

    assert q_tensor.format == QuantizationFormat.FP8_E4M3
    assert q_tensor.quantized_size_bytes == len(weights)
