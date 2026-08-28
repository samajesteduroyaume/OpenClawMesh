import time

from openclaw_mesh.crypto import NodeIdentity, TrustStore, verify_ed25519_signature
from openclaw_mesh.protocol import TaskRequest


def test_node_identity_generation_and_persistence(tmp_path):
    identity = NodeIdentity.generate()
    assert len(identity.public_key_hex) == 64
    assert len(identity.node_id) == 16

    key_file = tmp_path / "test_node.key"
    identity.save(key_file)
    assert key_file.is_file()

    loaded = NodeIdentity.load(key_file)
    assert loaded.public_key_hex == identity.public_key_hex
    assert loaded.node_id == identity.node_id


def test_ed25519_signing_and_verification():
    identity = NodeIdentity.generate()
    req = TaskRequest(
        skill="llm",
        payload={"prompt": "Bonjour monde"},
        origin="agent-alpha",
    )

    req.sign_ed25519(identity)
    assert req.pubkey == identity.public_key_hex
    assert req.sig is not None

    # Verify signature
    valid = verify_ed25519_signature(
        public_key_hex=req.pubkey,
        request_id=req.request_id,
        origin=req.origin,
        skill=req.skill,
        ts=req.ts,
        payload=req.payload,
        signature_hex=req.sig,
    )
    assert valid is True

    # Tampered origin should fail
    tampered_valid = verify_ed25519_signature(
        public_key_hex=req.pubkey,
        request_id=req.request_id,
        origin="imposter",
        skill=req.skill,
        ts=req.ts,
        payload=req.payload,
        signature_hex=req.sig,
    )
    assert tampered_valid is False

    # Timestamp drift check
    old_ts = time.time() - 400.0  # > 300s
    expired_valid = verify_ed25519_signature(
        public_key_hex=req.pubkey,
        request_id=req.request_id,
        origin=req.origin,
        skill=req.skill,
        ts=old_ts,
        payload=req.payload,
        signature_hex=req.sig,
    )
    assert expired_valid is False


def test_trust_store(tmp_path):
    id_alice = NodeIdentity.generate()
    id_bob = NodeIdentity.generate()

    store = TrustStore()
    assert store.is_trusted(id_alice.public_key_hex) is False

    store.trust(id_alice.public_key_hex)
    assert store.is_trusted(id_alice.public_key_hex) is True
    assert store.is_trusted(id_bob.public_key_hex) is False

    trust_file = tmp_path / "trust.json"
    store.save(trust_file)

    loaded_store = TrustStore.load(trust_file)
    assert loaded_store.is_trusted(id_alice.public_key_hex) is True
    assert loaded_store.is_trusted(id_bob.public_key_hex) is False

    loaded_store.revoke(id_alice.public_key_hex)
    assert loaded_store.is_trusted(id_alice.public_key_hex) is False
