"""Tests for High-Speed Binary Framing Wire Protocol."""

import pytest

from openclaw_mesh.network.binary_framing import (
    MSG_TYPE_STREAM_CHUNK,
    MSG_TYPE_TASK_REQUEST,
    BinaryFrame,
    FastBinaryStreamCodec,
)


def test_binary_frame_encode_decode():
    payload = b"Hello OpenClaw Binary World"
    frame = BinaryFrame(
        msg_type=MSG_TYPE_TASK_REQUEST,
        flags=0x00,
        payload=payload,
        sequence=42,
    )
    encoded = frame.encode()
    assert len(encoded) == 16 + len(payload)

    decoded_frame, bytes_consumed = BinaryFrame.decode(encoded)
    assert bytes_consumed == len(encoded)
    assert decoded_frame.msg_type == MSG_TYPE_TASK_REQUEST
    assert decoded_frame.sequence == 42
    assert decoded_frame.payload == payload


def test_binary_frame_tampered_crc_fails():
    payload = b"Important payload data"
    frame = BinaryFrame(
        msg_type=MSG_TYPE_TASK_REQUEST,
        flags=0x00,
        payload=payload,
    )
    encoded = bytearray(frame.encode())
    # Tamper payload
    encoded[-1] ^= 0xFF

    with pytest.raises(ValueError, match="CRC32 checksum mismatch"):
        BinaryFrame.decode(bytes(encoded))


def test_fast_binary_stream_codec():
    chunk_encoded = FastBinaryStreamCodec.encode_token_chunk(
        token=" distributed",
        index=3,
        is_final=False,
    )
    frame, _ = BinaryFrame.decode(chunk_encoded)
    assert frame.msg_type == MSG_TYPE_STREAM_CHUNK

    res = FastBinaryStreamCodec.decode_token_chunk(frame)
    assert res["token"] == " distributed"
    assert res["index"] == 3
    assert res["is_final"] is False
