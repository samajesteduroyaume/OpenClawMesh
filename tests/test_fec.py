from openclaw_mesh.network.fec import FECDecoder, FECEncoder


def test_fec_encode_and_complete_decode():
    payload = b"OpenClawMesh ultra-low latency token stream with FEC protection"
    blocks = FECEncoder.encode(payload, k_data_blocks=4, m_parity_blocks=2)

    assert len(blocks) == 6  # 4 data + 2 parity
    assert sum(1 for b in blocks if not b.is_parity) == 4
    assert sum(1 for b in blocks if b.is_parity) == 2

    # Decode with all blocks present
    decoder = FECDecoder(k_data_blocks=4, m_parity_blocks=2)
    for b in blocks:
        decoder.add_block(b)

    assert decoder.is_complete()
    decoded = decoder.decode()
    assert decoded == payload


def test_fec_recovery_with_lost_data_block():
    payload = b"Critical activation tensor chunk that experienced UDP packet loss"
    blocks = FECEncoder.encode(payload, k_data_blocks=4, m_parity_blocks=2)

    # Drop data block index 1 (simulate packet drop)
    received = [blocks[0], blocks[2], blocks[3], blocks[4]]  # 3 data + 1 parity

    decoder = FECDecoder(k_data_blocks=4, m_parity_blocks=2)
    for b in received:
        decoder.add_block(b)

    assert decoder.is_complete()
    decoded = decoder.decode()
    assert decoded == payload
