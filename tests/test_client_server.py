import asyncio
import pytest
from openclaw_mesh.node import OpenClawMeshNode
from openclaw_mesh.client import MeshClient
from openclaw_mesh.bridge import SkillRegistry, skill
from openclaw_mesh.crypto import NodeIdentity, TrustStore


def test_client_server_basic_exchange():
    async def _run():
        registry = SkillRegistry(name="test-server")

        @skill(name="add_numbers", description="Additionne deux nombres.")
        def add_numbers(payload: dict) -> dict:
            return {"result": payload.get("a", 0) + payload.get("b", 0)}

        @skill(name="stream_text", description="Streamer de texte.")
        async def stream_text(payload: dict):
            words = payload.get("text", "hello world mesh").split()
            for w in words:
                yield {"text": w + " "}
                await asyncio.sleep(0.01)

        registry.register(add_numbers)
        registry.register(stream_text)

        node = OpenClawMeshNode(
            name="test-node-1",
            port=8991,
            registry=registry,
        )
        await node.start(enable_zeroconf=False)

        client = MeshClient(name="test-client-1", enable_discovery=False)
        client.add_peer(name="test-node-1", address="127.0.0.1", port=8991, skills=["add_numbers", "stream_text"])

        try:
            # 1. Test describe skills
            desc = await client.discover_skills("test-node-1")
            assert "add_numbers" in desc["skills"]
            assert "stream_text" in desc["skills"]
            assert "echo" in desc["skills"]

            # 2. Test health probe
            health = await client.check_health("test-node-1")
            assert health["status"] == "ok"
            assert health["node_name"] == "test-node-1"

            # 3. Test synchronous skill call
            resp = await client.call("test-node-1", "add_numbers", {"a": 15, "b": 27})
            assert resp.ok is True
            assert resp.result == {"result": 42}
            assert resp.handled_by == "test-node-1"

            # 4. Test streaming skill call
            received_chunks = []
            def on_chunk(c):
                received_chunks.append(c.get("text", ""))

            stream_resp = await client.call_stream(
                "test-node-1",
                "stream_text",
                {"text": "OpenClaw and JarvisMesh P2P"},
                on_chunk=on_chunk,
            )
            assert stream_resp.ok is True
            assert stream_resp.streamed is True
            full_text = "".join(received_chunks).strip()
            assert full_text == "OpenClaw and JarvisMesh P2P"

            # 5. Test unknown skill error handling
            bad_resp = await client.call("test-node-1", "non_existent_skill", {})
            assert bad_resp.ok is False
            assert "Compétence inconnue" in bad_resp.error

        finally:
            await client.stop()
            await node.stop()

    asyncio.run(_run())


def test_client_server_hmac_auth():
    async def _run():
        psk = "shared_test_key_xyz"
        node = OpenClawMeshNode(name="secure-node", port=8992, psk=psk)
        await node.start(enable_zeroconf=False)

        # Client with correct PSK
        auth_client = MeshClient(name="auth-client", psk=psk, enable_discovery=False)
        auth_client.add_peer(name="secure-node", address="127.0.0.1", port=8992, skills=["echo"])

        # Client without PSK
        unauth_client = MeshClient(name="unauth-client", enable_discovery=False)
        unauth_client.add_peer(name="secure-node", address="127.0.0.1", port=8992, skills=["echo"])

        try:
            # Success with auth
            ok_resp = await auth_client.call("secure-node", "echo", {"msg": "secret"})
            assert ok_resp.ok is True
            assert ok_resp.result == {"msg": "secret"}

            # Failure without auth
            fail_resp = await unauth_client.call("secure-node", "echo", {"msg": "secret"})
            assert fail_resp.ok is False
            assert "Authentification échouée" in fail_resp.error

        finally:
            await auth_client.stop()
            await unauth_client.stop()
            await node.stop()

    asyncio.run(_run())


def test_client_server_ed25519_auth():
    async def _run():
        server_id = NodeIdentity.generate()
        client_id = NodeIdentity.generate()
        untrusted_id = NodeIdentity.generate()

        trust_store = TrustStore()
        trust_store.trust(client_id.public_key_hex)

        node = OpenClawMeshNode(
            name="ed25519-node",
            port=8993,
            identity=server_id,
            trust_store=trust_store,
        )
        await node.start(enable_zeroconf=False)

        trusted_client = MeshClient(name="trusted-client", identity=client_id, enable_discovery=False)
        trusted_client.add_peer("ed25519-node", "127.0.0.1", 8993, ["echo"])

        untrusted_client = MeshClient(name="untrusted-client", identity=untrusted_id, enable_discovery=False)
        untrusted_client.add_peer("ed25519-node", "127.0.0.1", 8993, ["echo"])

        try:
            # Trusted client succeeds
            ok_resp = await trusted_client.call("ed25519-node", "echo", {"test": "ed25519"})
            assert ok_resp.ok is True
            assert ok_resp.result == {"test": "ed25519"}

            # Untrusted client fails
            fail_resp = await untrusted_client.call("ed25519-node", "echo", {"test": "ed25519"})
            assert fail_resp.ok is False
            assert "Accès refusé" in fail_resp.error

        finally:
            await trusted_client.stop()
            await untrusted_client.stop()
            await node.stop()

    asyncio.run(_run())
