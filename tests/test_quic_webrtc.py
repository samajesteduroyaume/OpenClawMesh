import asyncio

import pytest

from openclaw_mesh.network.quic_webrtc import (
    PacketFlags,
    PacketType,
    QUICPacket,
    QUICWebRTCTransport,
)
from openclaw_mesh.protocol import TaskChunk, TaskRequest, TaskResponse


def test_quic_packet_pack_unpack():
    payload = b"Hello OpenClaw QUIC"
    pkt = QUICPacket(
        packet_type=PacketType.STREAM_DATA,
        stream_id=42,
        seq=1001,
        flags=PacketFlags.REQUIRES_ACK,
        payload=payload,
    )
    packed = pkt.pack()
    assert len(packed) > len(payload)

    unpacked = QUICPacket.unpack(packed)
    assert unpacked.packet_type == PacketType.STREAM_DATA
    assert unpacked.stream_id == 42
    assert unpacked.seq == 1001
    assert unpacked.flags == PacketFlags.REQUIRES_ACK
    assert unpacked.payload == payload


@pytest.mark.asyncio
async def test_quic_handshake_and_ping():
    server = QUICWebRTCTransport(
        node_name="server-quic", host="127.0.0.1", port=8910, psk="secret123"
    )
    client = QUICWebRTCTransport(
        node_name="client-quic", host="127.0.0.1", port=8911, psk="secret123"
    )

    s_host, s_port = await server.start()
    c_host, c_port = await client.start()

    try:
        session = await client.connect_session((s_host, s_port), timeout=2.0)
        assert session.is_established
        assert session.peer_name == "server-quic"

        # Ping RTT haute précision
        rtt_ms = await client.ping_peer((s_host, s_port), timeout=2.0)
        assert isinstance(rtt_ms, float)
        assert rtt_ms >= 0.0
        # En local, le RTT direct UDP est largement sub-10ms
        assert rtt_ms < 50.0

    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_quic_token_streaming_sub_10ms():
    server = QUICWebRTCTransport(node_name="stream-server", host="127.0.0.1", port=8912)
    client = QUICWebRTCTransport(node_name="stream-client", host="127.0.0.1", port=8913)

    received_tokens = []

    async def handle_stream_req(req: TaskRequest, stream):
        # Émettre 10 tokens en streaming direct UDP
        tokens = [
            "Bonjour",
            " le",
            " maillage",
            " décentralisé",
            " OpenClaw",
            " ultra",
            " rapide",
            " sub-10ms",
            " !",
            " FIN",
        ]
        for idx, tok in enumerate(tokens):
            chunk = TaskChunk(request_id=req.request_id, index=idx, chunk=tok)
            await server.send_stream_data(
                stream.session.peer_addr, stream.stream_id, chunk.to_json().encode("utf-8")
            )
        # Réponse finale
        resp = TaskResponse(
            request_id=req.request_id, ok=True, result={"tokens": len(tokens)}, streamed=True
        )
        await server.send_stream_data(
            stream.session.peer_addr, stream.stream_id, resp.to_json().encode("utf-8")
        )
        await server.send_stream_fin(stream.session.peer_addr, stream.stream_id)

    server.set_request_handler(handle_stream_req)

    s_host, s_port = await server.start()
    await client.start()

    try:
        req = TaskRequest(skill="stream_test", payload={"prompt": "test"})
        stream = await client.open_stream((s_host, s_port), req)

        received_tokens.extend([chunk_bytes async for chunk_bytes in stream.read_chunks()])

        assert len(received_tokens) == 11  # 10 chunks + 1 response
        assert stream.token_count == 11
        assert stream.first_token_latency_ms is not None
        # Latence premier token sub-10ms en local UDP
        assert stream.first_token_latency_ms < 50.0

    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_node_and_client_quic_streaming_e2e():
    """Vérifie l'intégration complète OpenClawMeshNode + MeshClient via streaming QUIC."""
    from openclaw_mesh.bridge import SkillRegistry
    from openclaw_mesh.client import MeshClient
    from openclaw_mesh.node import OpenClawMeshNode

    registry = SkillRegistry(name="quic-node")

    async def stream_tokens(payload):
        for token in ["OpenClaw", " QUIC", " Token", " Streaming", " Sub-10ms"]:
            await asyncio.sleep(0.001)
            yield token

    registry.register(stream_tokens, name="quic_stream_skill", expose_remote=True)

    node = OpenClawMeshNode(name="quic-node", port=8914, host="127.0.0.1", registry=registry)
    await node.start(enable_quic=True, quic_port=8915)

    client = MeshClient(name="quic-agent")
    await client.start(enable_quic=True)

    try:
        received = []

        def on_chunk(c):
            received.append(c)

        resp = await client.call_stream_quic(
            ("127.0.0.1", 8915),
            "quic_stream_skill",
            payload={"prompt": "go"},
            on_chunk=on_chunk,
            timeout=5.0,
        )

        assert resp.ok is True
        assert len(received) == 5
        assert "".join(received) == "OpenClaw QUIC Token Streaming Sub-10ms"

    finally:
        await client.stop()
        await node.stop()
