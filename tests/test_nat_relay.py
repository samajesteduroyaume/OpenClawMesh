import asyncio
import pytest
from openclaw_mesh.network.nat_traversal import discover_nat_and_public_ip, NATProfile
from openclaw_mesh.network.relay import WANRelayServer, WANRelayClient


def test_nat_profile_discovery():
    async def _run():
        profile = await discover_nat_and_public_ip(local_port=8770, timeout=0.5)
        assert isinstance(profile, NATProfile)
        assert profile.local_ip != ""
        assert profile.local_port == 8770
        assert profile.nat_type != ""

    asyncio.run(_run())


def test_wan_relay_server_and_client_communication():
    async def _run():
        relay_port = 8799
        relay = WANRelayServer(host="127.0.0.1", port=relay_port, name="test-relay")
        await relay.start()

        # Connecter deux clients : Alice et Bob
        alice = WANRelayClient(relay_url=f"ws://127.0.0.1:{relay_port}", node_id="alice_node_123", name="Alice")
        bob = WANRelayClient(relay_url=f"ws://127.0.0.1:{relay_port}", node_id="bob_node_456", name="Bob")

        assert await alice.connect() is True
        assert await bob.connect() is True

        received_payloads = []

        def on_bob_message(sender_id, payload):
            received_payloads.append((sender_id, payload))

        bob.on_message(on_bob_message)

        # Alice envoie un message relayé à Bob
        await alice.send_to_peer("bob_node_456", {"encrypted_data": "opaque_secret_payload"})
        await asyncio.sleep(0.1)

        assert len(received_payloads) == 1
        sender, content = received_payloads[0]
        assert sender == "alice_node_123"
        assert content == {"encrypted_data": "opaque_secret_payload"}

        # Nettoyage
        await alice.disconnect()
        await bob.disconnect()
        await relay.stop()

    asyncio.run(_run())
