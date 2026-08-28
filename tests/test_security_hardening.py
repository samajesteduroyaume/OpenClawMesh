import pytest

from openclaw_mesh.bridge import SkillRegistry
from openclaw_mesh.crypto import NodeIdentity
from openclaw_mesh.crypto_e2ee import E2EESession
from openclaw_mesh.engines.inference import UniversalInferenceEngine
from openclaw_mesh.gateway.db import KeyDatabase
from openclaw_mesh.gateway.portal import render_portal_html
from openclaw_mesh.network.dht import Contact, KademliaDHT


def test_system_diagnostics_are_not_exposed_remotely():
    registry = SkillRegistry()

    assert registry.get("system_info") is not None
    assert registry.is_remote_exposed("system_info") is False
    assert registry.is_remote_exposed("echo") is True
    assert registry.is_remote_exposed("openclaw_info") is False
    assert "openclaw_info" not in registry.describe()["skills"]


def test_portal_has_no_external_qr_or_font_resources():
    html = render_portal_html(btc_address="bc1qtest")

    assert "api.qrserver.com" not in html
    assert "fonts.googleapis.com" not in html
    assert "coinbase.com" not in html
    assert "bisq.network" not in html
    assert "data:image/svg+xml;base64," in html


def test_api_key_secret_is_not_persisted(tmp_path):
    database = KeyDatabase(tmp_path / "keys.db")
    record = database.create_key(email="secret@example.com")

    with database._get_connection() as connection:
        row = connection.execute("SELECT key, key_hash FROM api_keys").fetchone()

    assert row["key"] is None
    assert row["key_hash"]
    assert record.key not in str(dict(row))


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
