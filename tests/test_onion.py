from openclaw_mesh.crypto_e2ee import generate_ephemeral_keypair
from openclaw_mesh.network.onion import OnionHop, OnionRouter


def test_onion_multi_hop_circuit_routing():
    # Setup 3 nodes
    priv_a, pub_a = generate_ephemeral_keypair()
    priv_b, pub_b = generate_ephemeral_keypair()
    priv_c, pub_c = generate_ephemeral_keypair()

    router_a = OnionRouter(node_id="node-A", private_key_b64=priv_a)
    router_b = OnionRouter(node_id="node-B", private_key_b64=priv_b)
    router_c = OnionRouter(node_id="node-C", private_key_b64=priv_c)

    hops = [
        OnionHop(node_id="node-A", public_key_b64=pub_a),
        OnionHop(node_id="node-B", public_key_b64=pub_b),
        OnionHop(node_id="node-C", public_key_b64=pub_c),
    ]

    circuit_id = router_a.build_circuit(hops)
    payload = {"prompt": "Confidential AI request", "max_tokens": 128}

    # Wrap packet through circuit
    packet_to_a = router_a.wrap_onion(
        circuit_id=circuit_id,
        destination_node_id="destination-server",
        payload_data=payload,
    )

    # 1. Hop A unwraps
    status_a, next_hop_a, delivered_a, packet_to_b = router_a.unwrap_hop(packet_to_a)
    assert status_a == "FORWARD"
    assert next_hop_a == "node-B"
    assert delivered_a is None
    assert packet_to_b is not None

    # 2. Hop B unwraps
    status_b, next_hop_b, delivered_b, packet_to_c = router_b.unwrap_hop(packet_to_b)
    assert status_b == "FORWARD"
    assert next_hop_b == "node-C"
    assert delivered_b is None
    assert packet_to_c is not None

    # 3. Hop C unwraps (Final Hop)
    status_c, next_hop_c, delivered_c, packet_next = router_c.unwrap_hop(packet_to_c)
    assert status_c == "DELIVERED"
    assert delivered_c is not None
    assert delivered_c["prompt"] == "Confidential AI request"
    assert packet_next is None
