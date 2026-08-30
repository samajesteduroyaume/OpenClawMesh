from openclaw_mesh.network.ipv6_pcp import (
    IPv6Detector,
    NATPMPClient,
    PCPClient,
)


def test_ipv6_detector():
    addrs = IPv6Detector.get_global_ipv6_addresses()
    assert isinstance(addrs, list)
    assert len(addrs) >= 1
    assert any(":" in a for a in addrs)


def test_pcp_and_nat_pmp_packet_construction():
    # PCP RFC 6887 packet framing
    pcp_packet = PCPClient.create_map_request(
        internal_port=8765, protocol="udp", requested_lifetime=3600
    )
    assert len(pcp_packet) >= 60
    assert pcp_packet[0] == 2  # PCP version 2
    assert pcp_packet[1] == 1  # Opcode 1 (MAP)

    pcp_res = PCPClient.request_port_mapping("192.168.1.1", internal_port=8765)
    assert pcp_res.success is True
    assert pcp_res.external_port == 8765
    assert pcp_res.method == "pcp_rfc6887"

    # NAT-PMP packet framing
    nat_pmp_pkt = NATPMPClient.create_port_request(internal_port=8765, protocol="udp")
    assert len(nat_pmp_pkt) == 12
    assert nat_pmp_pkt[0] == 0  # NAT-PMP version 0

    pmp_res = NATPMPClient.request_port_mapping("192.168.1.1", internal_port=8765)
    assert pmp_res.success is True
    assert pmp_res.method == "nat_pmp"
