from openclaw_mesh.network.traffic_shaping import (
    MultipathOnionSharder,
    TrafficShaper,
)


def test_traffic_shaper_constant_padding():
    payload = b"User prompt: Summarize recent AI research in 2 paragraphs."
    padded = TrafficShaper.pad_payload(payload)

    assert padded.target_bucket_size in TrafficShaper.STANDARD_BUCKET_SIZES
    assert padded.target_bucket_size >= len(payload) + 4
    assert padded.padding_bytes_added > 0

    # Unpad
    recovered = TrafficShaper.unpad_payload(padded.padded_payload_b64)
    assert recovered == payload


def test_multipath_onion_sharding_and_reassembly():
    secret_prompt = b"Sensitive model prompt: Calculate financial forecast for Q3 without leakage."
    shards = MultipathOnionSharder.shard_payload(secret_prompt, num_shards=3)

    assert len(shards) == 3
    for s in shards:
        assert s["total_shards"] == 3
        assert "data_b64" in s

    # Reassemble shards
    reassembled = MultipathOnionSharder.reassemble_shards(shards)
    assert reassembled == secret_prompt
