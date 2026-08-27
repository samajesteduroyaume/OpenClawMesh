import pytest

from openclaw_mesh.bridge import SkillRegistry
from openclaw_mesh.engines.inference import UniversalInferenceEngine
from openclaw_mesh.crypto import NodeIdentity
from openclaw_mesh.crypto_e2ee import E2EESession
from openclaw_mesh.network.dht import Contact, KademliaDHT


def test_system_diagnostics_are_not_exposed_remotely():
    registry = SkillRegistry()

    assert registry.get("system_info") is not None
    assert registry.is_remote_exposed("system_info") is False
    assert registry.is_remote_exposed("echo") is True


def test_dht_rejects_invalid_storage_keys():
    dht = KademliaDHT(name="security-test")
    sender = Contact(node_id=dht.node_id, host="127.0.0.1", port=8799)

    with pytest.raises(ValueError):
        dht.rpc_store(sender, "", {"x": 1})


@pytest.mark.asyncio
async def test_inference_rejects_models_outside_allowlist():
    engine = UniversalInferenceEngine()

    with pytest.raises(ValueError, match="non autorisé"):
        await engine.generate("bonjour", model="attacker/untrusted-model")


def test_e2ee_strict_mode_requires_identity_binding():
    with pytest.raises(ValueError, match="identité locale"):
        E2EESession(require_identity_binding=True)

    alice_identity = NodeIdentity.generate()
    bob_identity = NodeIdentity.generate()
    alice = E2EESession(
        identity=alice_identity,
        peer_identity_public_key=bob_identity.public_key_hex,
        require_identity_binding=True,
    )
    bob = E2EESession(
        identity=bob_identity,
        peer_identity_public_key=alice_identity.public_key_hex,
        require_identity_binding=True,
    )
    alice.establish_with_peer(bob.public_key_bytes)
    bob.establish_with_peer(alice.public_key_bytes)

    assert bob.decrypt(alice.encrypt({"strict": True})) == {"strict": True}
