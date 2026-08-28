from openclaw_mesh.reputation import ReputationManager


def test_reputation_scoring_and_penalties(tmp_path):
    mgr = ReputationManager(min_eligible_score=0.5)

    node_id = "node_reliable_99"
    assert mgr.is_eligible(node_id) is True

    # 1. Succès
    score = mgr.record_success(node_id, latency_ms=45.0)
    assert score == 1.0

    # 2. Échecs consécutifs
    mgr.record_failure(node_id, reason="timeout")
    mgr.record_failure(node_id, reason="timeout")
    mgr.record_failure(node_id, reason="timeout")
    mgr.record_failure(node_id, reason="timeout")

    rec = mgr.get_record(node_id)
    assert rec.score < 0.5
    assert mgr.is_eligible(node_id) is False

    # 3. Dispute
    bad_node = "malicious_node_66"
    mgr.record_dispute(bad_node, reason="invalid_hmac")
    assert mgr.get_record(bad_node).score == 0.5

    # 4. Persistance
    save_path = tmp_path / "reputation.json"
    mgr.save_state(save_path)
    assert save_path.is_file()

    mgr2 = ReputationManager()
    restored = mgr2.load_state(save_path)
    assert restored >= 2
    assert mgr2.get_record(node_id).failed_calls == 4
