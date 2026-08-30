import pytest

from openclaw_mesh.network.multipath_routing import MultipathRouter, SelfHealingController


def test_multipath_router_selection():
    router = MultipathRouter(local_node_id="node-alice")

    # Register 3 candidate paths
    router.register_path(
        target_node_id="node-bob", endpoint="192.168.1.50:8765", initial_rtt_ms=12.0
    )
    router.register_path(target_node_id="node-bob", endpoint="10.0.0.80:8765", initial_rtt_ms=45.0)
    router.register_path(
        target_node_id="node-bob", endpoint="relay.openclaw.io:8765", initial_rtt_ms=80.0
    )

    best = router.select_best_path(target_node_id="node-bob")
    assert best is not None
    assert best.endpoint == "192.168.1.50:8765"
    assert best.rtt_ms == 12.0

    bundle = router.select_multipath_bundle(target_node_id="node-bob", bundle_size=2)
    assert len(bundle) == 2
    assert bundle[0].endpoint == "192.168.1.50:8765"
    assert bundle[1].endpoint == "10.0.0.80:8765"


@pytest.mark.asyncio
async def test_self_healing_failover():
    router = MultipathRouter(local_node_id="node-alice")
    router.register_path(target_node_id="node-bob", endpoint="direct-lan:8765", initial_rtt_ms=10.0)
    router.register_path(target_node_id="node-bob", endpoint="wan-relay:8765", initial_rtt_ms=35.0)

    controller = SelfHealingController(router=router)
    bound_ep = controller.bind_session(session_id="sess-42", target_node_id="node-bob")
    assert bound_ep == "direct-lan:8765"

    # Simulate link failure
    new_ep = await controller.handle_link_failure(
        session_id="sess-42",
        target_node_id="node-bob",
        failed_endpoint="direct-lan:8765",
    )
    assert new_ep == "wan-relay:8765"
    assert len(controller.failover_events) == 1
    assert controller.failover_events[0]["failover_latency_ms"] < 50.0
