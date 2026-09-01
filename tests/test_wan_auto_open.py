import pytest
from unittest.mock import AsyncMock, patch

from openclaw_mesh.config import Settings, get_settings, reload_settings
from openclaw_mesh.network.nat_traversal import (
    NATProfile,
    auto_map_all_wan_ports,
    discover_nat_and_public_ip,
)
from openclaw_mesh.node import OpenClawMeshNode


@pytest.mark.asyncio
async def test_wan_enabled_by_default_settings():
    settings = reload_settings()
    assert settings.wan_enabled is True
    assert settings.upnp_enabled is True
    assert settings.pcp_enabled is True
    assert settings.dht_enabled is True
    assert settings.default_host == "0.0.0.0"


@pytest.mark.asyncio
async def test_auto_map_all_wan_ports():
    with patch("openclaw_mesh.network.nat_traversal.auto_map_upnp_port", new=AsyncMock(return_value=True)) as mock_upnp:
        res = await auto_map_all_wan_ports(tcp_ports=[8770, 8000], udp_ports=[8775, 8780])
        assert res["tcp"][8770] is True
        assert res["tcp"][8000] is True
        assert res["udp"][8775] is True
        assert res["udp"][8780] is True
        assert mock_upnp.call_count == 4


@pytest.mark.asyncio
async def test_discover_nat_and_public_ip_auto_open():
    with patch("openclaw_mesh.network.nat_traversal.auto_map_all_wan_ports", new=AsyncMock(return_value={"tcp": {8770: True}, "udp": {8775: True, 8780: True}})):
        profile = await discover_nat_and_public_ip(
            local_port=8770,
            enabled=True,
            try_upnp=True,
            extra_udp_ports=[8775, 8780],
            timeout=0.1,
            stun_servers=[],
        )
        assert isinstance(profile, NATProfile)
        assert profile.upnp_mapped is True


@pytest.mark.asyncio
async def test_node_start_with_default_wan():
    node = OpenClawMeshNode(name="wan-auto-node", port=8988, host="127.0.0.1")
    with patch("openclaw_mesh.network.nat_traversal.discover_nat_and_public_ip", new=AsyncMock(return_value=NATProfile(
        public_ip="198.51.100.1",
        public_port=8988,
        local_ip="192.168.1.50",
        local_port=8988,
        nat_type="UPnP Mapped",
        is_direct_connectable=True,
        upnp_mapped=True,
    ))) as mock_nat:
        await node.start(enable_zeroconf=False, enable_quic=False, enable_gossipsub=False, enable_dht=False)
        try:
            assert node._running is True
            assert node._nat_profile is not None
            assert node._nat_profile.upnp_mapped is True
            assert node._nat_profile.public_ip == "198.51.100.1"
            assert mock_nat.called
        finally:
            await node.stop()
