import pytest

from openclaw_mesh.network.gossipsub import (
    ControlMessage,
    GossipMessage,
    GossipSubNode,
    MessageCache,
)


def test_gossip_message_id_and_cache():
    msg = GossipMessage(
        topic="openclaw/v1/models",
        data={"model": "Qwen2.5-Coder-7B", "vram": 4096},
        from_peer="node-alice",
        seq=1,
    )
    assert len(msg.msg_id) == 24

    cache = MessageCache(history_length=3, gossip_window=2)
    cache.put(msg)
    assert cache.get(msg.msg_id) == msg
    assert msg.msg_id in cache.get_gossip_msg_ids("openclaw/v1/models")

    # Shift de cache
    cache.shift()
    assert cache.get(msg.msg_id) == msg
    cache.shift()
    cache.shift()
    cache.shift()
    # Après expiration
    assert cache.get(msg.msg_id) is None


@pytest.mark.asyncio
async def test_gossipsub_publish_and_receive():
    received_alice = []
    received_bob = []

    # Création de 2 nœuds reliés en mémoire
    alice = GossipSubNode(node_id="peer-alice", node_name="alice")
    bob = GossipSubNode(node_id="peer-bob", node_name="bob")

    async def send_to_bob(ep, wire):
        await bob.handle_incoming(wire, "memory://alice")

    async def send_to_alice(ep, wire):
        await alice.handle_incoming(wire, "memory://bob")

    alice.send_fn = send_to_bob
    bob.send_fn = send_to_alice

    alice.add_peer("peer-bob", "memory://bob")
    bob.add_peer("peer-alice", "memory://alice")

    alice.subscribe("openclaw/v1/discovery", lambda m: received_alice.append(m))
    bob.subscribe("openclaw/v1/discovery", lambda m: received_bob.append(m))

    await alice.start()
    await bob.start()

    try:
        # Alice publie un message
        msg_id = await alice.publish(
            "openclaw/v1/discovery", {"status": "online", "skills": ["vision", "llm"]}
        )
        assert msg_id

        # Vérification de réception
        assert len(received_alice) == 1
        assert len(received_bob) == 1
        assert received_bob[0].data["status"] == "online"
        assert received_bob[0].from_peer == "peer-alice"

    finally:
        await alice.stop()
        await bob.stop()


@pytest.mark.asyncio
async def test_gossipsub_graft_prune_lazy_ihave_iwant():
    alice = GossipSubNode(node_id="alice", d=2, d_low=1, d_high=3)
    bob = GossipSubNode(node_id="bob", d=2, d_low=1, d_high=3)

    bob_requests = []

    async def send_to_bob(ep, wire):
        await bob.handle_incoming(wire, "memory://alice")

    async def send_to_alice(ep, wire):
        ctrl = wire.get("control", {})
        if "iwant" in ctrl and ctrl["iwant"]:
            bob_requests.extend(ctrl["iwant"])
        await alice.handle_incoming(wire, "memory://bob")

    alice.send_fn = send_to_bob
    bob.send_fn = send_to_alice

    alice.add_peer("bob", "memory://bob")
    bob.add_peer("alice", "memory://alice")

    # Bob souscrit
    bob.subscribe("test-topic")

    # Simuler un IHAVE reçu par Bob depuis Alice
    ihave_ctrl = ControlMessage(ihave=[{"topic": "test-topic", "msg_ids": ["unknown_msg_123"]}])
    wire_ihave = alice._pack_wire_message(control=ihave_ctrl)

    await bob.handle_incoming(wire_ihave, "memory://alice")

    # Bob doit avoir émis un IWANT pour unknown_msg_123
    assert "unknown_msg_123" in bob_requests
