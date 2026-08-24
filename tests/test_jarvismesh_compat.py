import asyncio
import sys
import pytest
from pathlib import Path

# Importer jarvismesh depuis le bureau
JARVISMESH_PATH = Path("/Users/selim/Desktop/jarvismesh")
if str(JARVISMESH_PATH) not in sys.path:
    sys.path.insert(0, str(JARVISMESH_PATH))

try:
    import jarvismesh.core.protocol as jm_proto
    import jarvismesh.security.crypto as jm_crypto
    import jarvismesh.core.node as jm_node
    _HAS_JARVISMESH = True
except ImportError:
    _HAS_JARVISMESH = False

import openclaw_mesh.protocol as oc_proto
import openclaw_mesh.crypto as oc_crypto
from openclaw_mesh.client import MeshClient
from openclaw_mesh.node import OpenClawMeshNode
from openclaw_mesh.bridge import SkillRegistry, skill


@pytest.mark.skipif(not _HAS_JARVISMESH, reason="JarvisMesh n'est pas disponible sur le système")
def test_protocol_cross_verification_hmac():
    psk = "mesh_cross_test_secret_key"
    payload = {"query": "cross validation", "data": [1, 2, 3], "nested": {"a": True}}

    # 1. OpenClaw signe -> JarvisMesh vérifie
    oc_req = oc_proto.TaskRequest(skill="search", payload=payload, origin="openclaw-node")
    oc_req.sign(psk)

    jm_verified = jm_proto.verify_request(
        psk=psk,
        request_id=oc_req.request_id,
        origin=oc_req.origin,
        skill=oc_req.skill,
        ts=oc_req.ts,
        payload=oc_req.payload,
        signature=oc_req.sig,
    )
    assert jm_verified is True

    # 2. JarvisMesh signe -> OpenClaw vérifie
    jm_req = jm_proto.TaskRequest(skill="search", payload=payload, origin="jarvis-node")
    jm_req.sign(psk)

    oc_verified = oc_proto.verify_request(
        psk=psk,
        request_id=jm_req.request_id,
        origin=jm_req.origin,
        skill=jm_req.skill,
        ts=jm_req.ts,
        payload=jm_req.payload,
        signature=jm_req.sig,
    )
    assert oc_verified is True


@pytest.mark.skipif(not _HAS_JARVISMESH, reason="JarvisMesh n'est pas disponible sur le système")
def test_crypto_cross_verification_ed25519():
    oc_id = oc_crypto.NodeIdentity.generate()
    jm_id = jm_crypto.NodeIdentity.generate()
    payload = {"instruction": "execute mesh task", "tokens": 128}

    # 1. OpenClaw NodeIdentity signe -> JarvisMesh verify_ed25519_signature vérifie
    oc_req = oc_proto.TaskRequest(skill="llm", payload=payload, origin="openclaw-agent")
    oc_req.sign_ed25519(oc_id)

    jm_valid = jm_crypto.verify_ed25519_signature(
        public_key_hex=oc_req.pubkey,
        request_id=oc_req.request_id,
        origin=oc_req.origin,
        skill=oc_req.skill,
        ts=oc_req.ts,
        payload=oc_req.payload,
        signature_hex=oc_req.sig,
    )
    assert jm_valid is True

    # 2. JarvisMesh NodeIdentity signe -> OpenClaw verify_ed25519_signature vérifie
    jm_req = jm_proto.TaskRequest(skill="llm", payload=payload, origin="jarvis-agent")
    jm_req.sign_ed25519(jm_id)

    oc_valid = oc_crypto.verify_ed25519_signature(
        public_key_hex=jm_req.pubkey,
        request_id=jm_req.request_id,
        origin=jm_req.origin,
        skill=jm_req.skill,
        ts=jm_req.ts,
        payload=jm_req.payload,
        signature_hex=jm_req.sig,
    )
    assert oc_valid is True


@pytest.mark.skipif(not _HAS_JARVISMESH, reason="JarvisMesh n'est pas disponible sur le système")
def test_openclaw_client_to_jarvismesh_node():
    """Vérifie qu'un MeshClient OpenClaw peut interroger directement un JarvisNode réel."""
    async def _run():
        def sample_jarvis_skill(payload: dict) -> dict:
            return {"jarvis_response": f"Processed: {payload.get('text')}"}

        jarvis_node = jm_node.JarvisNode(
            name="jarvis-real-node",
            port=8995,
            skills={"jarvis_skill": sample_jarvis_skill},
        )
        await jarvis_node.start(enable_zeroconf=False)

        oc_client = MeshClient(name="openclaw-caller", enable_discovery=False)
        oc_client.add_peer("jarvis-real-node", "127.0.0.1", 8995, ["jarvis_skill"])

        try:
            # Appel depuis OpenClaw vers JarvisMesh
            resp = await oc_client.call("jarvis-real-node", "jarvis_skill", {"text": "Hello from OpenClaw"})
            assert resp.ok is True
            assert resp.result == {"jarvis_response": "Processed: Hello from OpenClaw"}
            assert resp.handled_by == "jarvis-real-node"

            # Introspection réservée _describe_skills
            desc = await oc_client.discover_skills("jarvis-real-node")
            assert "jarvis_skill" in desc["skills"]

            # Health probe réservée _health
            health = await oc_client.check_health("jarvis-real-node")
            assert "active_tasks" in health
            assert "rtt_ms" in health

        finally:
            await oc_client.stop()
            await jarvis_node.stop()

    asyncio.run(_run())


@pytest.mark.skipif(not _HAS_JARVISMESH, reason="JarvisMesh n'est pas disponible sur le système")
def test_jarvismesh_node_to_openclaw_node():
    """Vérifie qu'un JarvisNode peut déléguer une tâche à un OpenClawMeshNode."""
    async def _run():
        reg = SkillRegistry(name="openclaw-provider")

        @skill(name="claw_processor", description="Compétence fournie par OpenClaw.")
        def claw_processor(payload: dict) -> dict:
            return {"status": "success", "doubled": payload.get("val", 0) * 2}

        reg.register(claw_processor)

        oc_node = OpenClawMeshNode(name="openclaw-server", port=8996, registry=reg)
        await oc_node.start(enable_zeroconf=False)

        jarvis_caller = jm_node.JarvisNode(name="jarvis-client", port=8997)
        jarvis_caller.add_static_peer("openclaw-server", "127.0.0.1", 8996, ["claw_processor"])
        await jarvis_caller.start(enable_zeroconf=False)

        try:
            # JarvisNode appelle OpenClawMeshNode via delegate
            resp = await jarvis_caller.delegate("claw_processor", {"val": 21}, peer_name="openclaw-server")
            assert resp.ok is True
            assert resp.result == {"status": "success", "doubled": 42}
            assert resp.handled_by == "openclaw-server"

        finally:
            await jarvis_caller.stop()
            await oc_node.stop()

    asyncio.run(_run())
