import pytest

from openclaw_mesh.security.pqc_kem import HybridKeyPair, HybridPQCManager


def test_pqc_keypair_generation():
    keypair = HybridPQCManager.generate_keypair()
    assert isinstance(keypair, HybridKeyPair)
    assert len(keypair.x25519_private_bytes) == 32
    assert len(keypair.x25519_public_bytes) == 32
    assert len(keypair.pqc_private_bytes) == 32
    assert len(keypair.pqc_public_bytes) == 32
    assert len(keypair.public_key_b64) > 80


def test_pqc_encapsulate_decapsulate_success():
    receiver = HybridPQCManager()
    sender_enc = HybridPQCManager.encapsulate(receiver.keypair.public_key_b64)

    assert len(sender_enc.shared_secret) == 32
    assert sender_enc.ephemeral_public_b64
    assert sender_enc.pqc_ciphertext_b64

    # Recipient decapsulates
    receiver_secret = receiver.decapsulate(
        sender_enc.ephemeral_public_b64,
        sender_enc.pqc_ciphertext_b64,
    )

    assert receiver_secret == sender_enc.shared_secret


def test_pqc_decapsulate_tampered_fails():
    receiver = HybridPQCManager()
    sender_enc = HybridPQCManager.encapsulate(receiver.keypair.public_key_b64)

    # Tamper with ciphertext
    import base64

    raw_ct = bytearray(base64.b64decode(sender_enc.pqc_ciphertext_b64))
    raw_ct[5] ^= 0xFF
    tampered_b64 = base64.b64encode(raw_ct).decode("utf-8")

    with pytest.raises(ValueError, match="integrity failure"):
        receiver.decapsulate(
            sender_enc.ephemeral_public_b64,
            tampered_b64,
        )
