from openclaw_mesh.network.dht_rendezvous import DHTRendezvousManager


def test_dht_rendezvous_registration_and_planning():
    mgr_alice = DHTRendezvousManager(node_id="peer-alice")
    rec = mgr_alice.create_record(
        public_endpoints=["198.51.100.22:45000", "203.0.113.10:45000"],
        ephemeral_pubkey="pub-eph-alice-hex-1234",
    )

    assert rec.node_id == "peer-alice"
    assert not rec.is_expired
    assert len(rec.public_endpoints) == 2

    # Bob caches Alice's rendezvous record
    mgr_bob = DHTRendezvousManager(node_id="peer-bob")
    mgr_bob.store_remote_record(rec)

    found = mgr_bob.get_record("peer-alice")
    assert found is not None
    assert found.ephemeral_pubkey == "pub-eph-alice-hex-1234"

    # Plan synchronized hole punch
    plan = mgr_bob.plan_hole_punch("peer-alice", lead_time_ms=300)
    assert plan is not None
    assert plan["target_node_id"] == "peer-alice"
    assert "sync_punch_timestamp" in plan
    assert plan["lead_time_ms"] == 300
