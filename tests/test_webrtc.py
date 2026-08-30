import pytest

from openclaw_mesh.network.webrtc import (
    WebRTCChannel,
    WebRTCSignalingManager,
)


@pytest.mark.asyncio
async def test_webrtc_channel_send_receive():
    received_items = []

    async def on_msg(data):
        received_items.append(data)

    ch = WebRTCChannel(channel_id="test-ch-1", label="stream", on_message_callback=on_msg)
    await ch.open()
    assert ch.is_open

    # Feed data
    await ch.feed_incoming(b"token-chunk-1")
    assert len(received_items) == 1
    assert received_items[0] == b"token-chunk-1"

    # Receive from queue
    item = await ch.receive(timeout=1.0)
    assert item == b"token-chunk-1"

    # Send data
    await ch.send("hello peer")
    sent = await ch._send_queue.get()
    assert sent == "hello peer"
    assert ch.packets_sent == 1

    await ch.close()
    assert not ch.is_open


@pytest.mark.asyncio
async def test_webrtc_signaling_offer_answer():
    sig_mgr = WebRTCSignalingManager(node_id="peer-alice")

    offer = await sig_mgr.create_offer("peer-bob")
    assert offer.sdp_type == "offer"
    assert "webrtc-datachannel" in offer.sdp

    answer = await sig_mgr.handle_offer("peer-bob", offer)
    assert answer.sdp_type == "answer"
    assert answer.session_id == offer.session_id

    stats = sig_mgr.get_stats()
    assert stats["node_id"] == "peer-alice"
