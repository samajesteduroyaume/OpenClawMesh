import time

import pytest
from cryptography.exceptions import InvalidTag

from openclaw_mesh.crypto import NodeIdentity
from openclaw_mesh.crypto_e2ee import (
    E2EESession,
    ReplayError,
    decrypt_message_with_key,
    encrypt_message_for_peer,
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

    with pytest.raises(InvalidTag):
        bob.decrypt(pkg)


def test_e2ee_replay_detection_same_nonce_rejected():
    """Un paquet capturé et réinjecté immédiatement est rejeté par le cache de nonces."""
    alice = E2EESession()
    bob = E2EESession()
    alice.establish_with_peer(bob.public_key_bytes)
    bob.establish_with_peer(alice.public_key_bytes)

    pkg = alice.encrypt({"cmd": "launch_sequential"})
    # Première réception légitime
    assert bob.decrypt(pkg) == {"cmd": "launch_sequential"}

    # Rejeu du même paquet → rejeté anti-rejeu
    with pytest.raises(ReplayError):
        bob.decrypt(pkg)


def test_e2ee_stale_timestamp_rejected():
    """Un paquet dont l'horodatage est en dehors de la fenêtre de tolérance est rejeté."""
    alice = E2EESession()
    bob = E2EESession()
    alice.establish_with_peer(bob.public_key_bytes)
    bob.establish_with_peer(alice.public_key_bytes)

    pkg = alice.encrypt({"cmd": "run_task"})
    # Simulation d'un paquet capturé et réinjecté 600s plus tard (hors fenêtre)
    pkg["timestamp"] = time.time() - 600
    with pytest.raises(ReplayError):
        bob.decrypt(pkg)


def test_e2ee_future_timestamp_rejected():
    """Un paquet dont l'horodatage est trop en avance est rejeté (anti-rejeu/freshness)."""
    alice = E2EESession()
    bob = E2EESession()
    alice.establish_with_peer(bob.public_key_bytes)
    bob.establish_with_peer(alice.public_key_bytes)

    pkg = alice.encrypt({"cmd": "run_task"})
    pkg["timestamp"] = time.time() + 600
    with pytest.raises(ReplayError):
        bob.decrypt(pkg)


def test_e2ee_replay_cache_disabled_accepting_replay():
    """Sans cache de nonces, le replay est uniquement contrôlé par l'horodatage."""
    alice = E2EESession()
    bob = E2EESession()
    alice.establish_with_peer(bob.public_key_bytes)
    # Désactivation du cache de nonces mais horodatage valide
    bob_cacheless = E2EESession(
        local_private_key=bob._private_key,
        peer_public_key_bytes=alice.public_key_bytes,
        enable_nonce_replay=False,
    )
    pkg = alice.encrypt({"cmd": "replay_allowed"})
    assert bob_cacheless.decrypt(pkg) == {"cmd": "replay_allowed"}
    # Rejeu accepté car le cache de nonces est désactivé
    assert bob_cacheless.decrypt(pkg) == {"cmd": "replay_allowed"}


def test_e2ee_unique_nonces_no_collision():
    """Deux encryptions successives produisent des nonces distincts."""
    alice = E2EESession()
    bob = E2EESession()
    alice.establish_with_peer(bob.public_key_bytes)
    bob.establish_with_peer(alice.public_key_bytes)

    pkg1 = alice.encrypt({"n": 1})
    pkg2 = alice.encrypt({"n": 2})
    assert pkg1["nonce"] != pkg2["nonce"]
    assert bob.decrypt(pkg1) == {"n": 1}
    assert bob.decrypt(pkg2) == {"n": 2}


def test_e2ee_stateless_helper_timestamp_enforced():
    """Le helper stateless déclenche une erreur sur un horodatage périmé."""
    alice = E2EESession()
    pkg = encrypt_message_for_peer(alice.public_key_hex, {"msg": "hi"})
    pkg["timestamp"] = time.time() - 9999
    with pytest.raises(ReplayError):
        decrypt_message_with_key(alice._private_key.private_bytes_raw(), pkg)


def test_e2ee_authenticated_identity_rejects_tampering():
    """L’identité Ed25519 authentifie la clé de session et ses métadonnées."""
    alice_identity = NodeIdentity.generate()
    bob_identity = NodeIdentity.generate()
    alice = E2EESession(
        identity=alice_identity,
        peer_identity_public_key=bob_identity.public_key_hex,
    )
    bob = E2EESession(
        identity=bob_identity,
        peer_identity_public_key=alice_identity.public_key_hex,
    )
    alice.establish_with_peer(bob.public_key_bytes)
    bob.establish_with_peer(alice.public_key_bytes)

    package = alice.encrypt({"authenticated": True})
    assert bob.decrypt(package) == {"authenticated": True}

    package["identity_signature"] = "00" * 64
    with pytest.raises(ReplayError):
        bob.decrypt(package)
