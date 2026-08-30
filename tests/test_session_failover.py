"""Tests for Zero-Drop Session Failover & Live KV-Cache Migration."""

from openclaw_mesh.network.session_failover import SessionFailoverController


def test_session_failover_and_kv_cache_migration():
    controller = SessionFailoverController()
    session_id = "sess_stream_001"
    prompt = "Écris un poème sur la décentralisation"

    sess = controller.register_session(
        session_id=session_id,
        prompt=prompt,
        primary_node_id="primary-gpu-node",
    )
    assert sess.current_node_id == "primary-gpu-node"

    # Primary generates some tokens
    controller.append_generated_token(session_id, "Dans ")
    controller.append_generated_token(session_id, "le ")
    controller.append_generated_token(session_id, "réseau ")
    assert len(sess.tokens_generated) == 3

    # Simulate primary failure & hot failover to backup node
    failover_ok, reason = controller.trigger_failover_if_needed(
        session_id=session_id,
        backup_node_id="backup-metal-node",
        is_primary_alive=False,
    )
    assert failover_ok is True
    assert "backup-metal-node" in reason

    # Verify session now points to backup node with all tokens preserved
    updated_sess = controller.get_session(session_id)
    assert updated_sess is not None
    assert updated_sess.current_node_id == "backup-metal-node"
    assert len(updated_sess.tokens_generated) == 3
