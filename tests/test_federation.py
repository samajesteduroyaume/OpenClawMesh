from openclaw_mesh.network.federation import FederationBridge


def test_federation_bridge_and_acl_routing():
    bridge = FederationBridge(local_domain_id="domain-alpha")

    # Register external federated cluster
    domain_beta = bridge.register_domain(
        domain_id="domain-beta",
        name="Community DeepSeek Cluster",
        gateway_endpoint="https://beta.mesh.openclaw.io",
        allowed_skills=["deepseek_r1_reasoning", "web_search"],
        public_key_hex="a1b2c3d4e5f6...",
    )

    assert domain_beta.domain_id == "domain-beta"

    # Local access is always allowed
    assert bridge.check_access("domain-alpha", "any_skill") is True

    # Domain beta allowed skills
    assert bridge.check_access("domain-beta", "deepseek_r1_reasoning") is True
    assert bridge.check_access("domain-beta", "web_search") is True
    assert bridge.check_access("domain-beta", "unauthorized_admin_tool") is False

    # Route skill
    routed_domain = bridge.route_federated_skill("deepseek_r1_reasoning")
    assert routed_domain is not None
    assert routed_domain.domain_id == "domain-beta"
