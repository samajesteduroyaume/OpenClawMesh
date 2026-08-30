from openclaw_mesh.network.gossip import GossipProtocol, NodeMetrics


def test_gossip_metrics_packaging_and_signature():
    psk = "shared_gossip_secret_key"
    gossip_a = GossipProtocol(node_name="node-paris", node_id="node_id_1111", psk=psk)
    gossip_b = GossipProtocol(node_name="node-tokyo", node_id="node_id_2222", psk=psk)

    # 1. Update local metrics
    gossip_a.update_local_metrics(
        cpu_percent=12.5,
        memory_percent=45.0,
        vram_free_mb=16384,
        active_tasks=1,
        capacity=20,
        skills=["llm", "vision"],
        endpoint="ws://10.0.0.1:8770",
        reputation_score=0.98,
    )

    # 2. Pack rumor message
    msg = gossip_a.pack_gossip_message()
    assert msg["type"] == "gossip_rumor"
    assert "_sig" in msg
    assert len(msg["metrics"]) >= 1

    # 3. Process rumor on node B
    updated = gossip_b.process_incoming_gossip(msg)
    assert updated is True

    cluster_b = gossip_b.get_cluster_metrics()
    assert "node_id_1111" in cluster_b
    assert cluster_b["node_id_1111"].cpu_percent == 12.5
    assert cluster_b["node_id_1111"].vram_free_mb == 16384

    # 4. Tampered message rejection
    msg_tampered = dict(msg)
    msg_tampered["metrics"] = [{"node_id": "fake", "node_name": "fake", "cpu_percent": 99.0}]
    assert gossip_b.process_incoming_gossip(msg_tampered) is False


def test_gossip_best_node_selection():
    gossip = GossipProtocol(node_name="orchestrator", node_id="orch_0")
    gossip.update_local_metrics(
        cpu_percent=80.0, vram_free_mb=0, active_tasks=5, capacity=5, skills=["llm"]
    )

    # Simuler deux pairs découverts
    gossip._cluster_metrics["gpu_node_1"] = NodeMetrics(
        node_name="gpu-heavy-1",
        node_id="gpu_node_1",
        cpu_percent=20.0,
        vram_free_mb=24000,
        active_tasks=0,
        capacity=10,
        skills=["llm", "moe"],
        reputation_score=1.0,
    )
    gossip._cluster_metrics["gpu_node_2"] = NodeMetrics(
        node_name="gpu-heavy-2",
        node_id="gpu_node_2",
        cpu_percent=70.0,
        vram_free_mb=8000,
        active_tasks=4,
        capacity=5,
        skills=["llm"],
        reputation_score=0.8,
    )

    best = gossip.get_best_node_for_task(required_skill="moe")
    assert best is not None
    assert best.node_id == "gpu_node_1"
