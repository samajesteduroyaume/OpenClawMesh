import pytest
from openclaw_mesh.crypto_e2ee import (
    E2EESession,
    encrypt_message_for_peer,
    decrypt_message_with_key,
)


def test_e2ee_session_establishment_and_exchange():
    # Deux pairs : Alice et Bob
    alice_session = E2EESession()
    bob_session = E2EESession()

    # Échange des clés publiques X25519
    alice_session.establish_with_peer(bob_session.public_key_bytes)
    bob_session.establish_with_peer(alice_session.public_key_bytes)

    assert alice_session.is_established
    assert bob_session.is_established

    # 1. Alice chiffre un payload JSON pour Bob
    secret_payload = {"prompt": "Deploy secure agent cluster", "nodes": 5, "is_private": True}
    encrypted_pkg = alice_session.encrypt(secret_payload)

    assert "ciphertext" in encrypted_pkg
    assert "nonce" in encrypted_pkg
    assert encrypted_pkg["algorithm"] == "ChaCha20-Poly1305"

    # 2. Bob déchiffre le message
    decrypted = bob_session.decrypt(encrypted_pkg)
    assert decrypted == secret_payload


def test_e2ee_direct_helper_functions():
    alice_session = E2EESession()
    bob_session = E2EESession()

    msg = "Top secret instructions for autonomous agent"
    encrypted = encrypt_message_for_peer(bob_session.public_key_hex, msg)

    # Bob déchiffre
    decrypted = decrypt_message_with_key(bob_session._private_key.private_bytes_raw(), encrypted)
    assert decrypted == msg


def test_e2ee_tamper_detection():
    alice = E2EESession()
    bob = E2EESession()
    alice.establish_with_peer(bob.public_key_bytes)
    bob.establish_with_peer(alice.public_key_bytes)

    pkg = alice.encrypt({"data": "original"})

    # Altération frauduleuse du ciphertext (Attaque Man-in-the-Middle sur le relais)
    corrupted_bytes = bytearray(bytes.fromhex(pkg["ciphertext"]))
    corrupted_bytes[0] ^= 0xFF
    pkg["ciphertext"] = corrupted_bytes.hex()

    with pytest.raises(Exception):
        bob.decrypt(pkg)
