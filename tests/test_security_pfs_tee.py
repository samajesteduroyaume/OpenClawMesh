import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from openclaw_mesh.crypto_e2ee import (
    derive_shared_key,
    generate_ephemeral_keypair,
)
from openclaw_mesh.security.pfs_ratchet import PFSRatchetSession
from openclaw_mesh.security.tee_enclave import (
    ConfidentialEnclave,
    EnclaveVerifier,
    TEEType,
)


def test_tee_attestation_and_execution():
    enclave = ConfidentialEnclave(node_id="enclave-node-1", enclave_type=TEEType.AMD_SEV)
    nonce = "challenge_client_nonce_99"

    report = enclave.generate_attestation_report(client_nonce=nonce)
    assert EnclaveVerifier.verify_attestation(report, expected_nonce=nonce) is True
    assert EnclaveVerifier.verify_attestation(report, expected_nonce="wrong_nonce") is False

    # Encrypt prompt for enclave
    client_priv, client_pub = generate_ephemeral_keypair()
    shared_key = derive_shared_key(client_priv, enclave.pub_key)
    chacha = ChaCha20Poly1305(shared_key)
    c_nonce = os.urandom(12)
    c_text = chacha.encrypt(c_nonce, b"Private confidential query", None)
    enc_b64 = base64.b64encode(c_nonce + c_text).decode("utf-8")

    res = enclave.execute_confidential_inference(enc_b64, client_pub)
    assert res["status"] == "success"
    assert "encrypted_result_b64" in res


def test_pfs_double_ratchet_session():
    shared_master = b"\x01" * 32
    alice = PFSRatchetSession(
        session_id="sess-1", initial_shared_secret=shared_master, is_initiator=True
    )
    bob = PFSRatchetSession(
        session_id="sess-1", initial_shared_secret=shared_master, is_initiator=False
    )

    # Alice sends message 1
    msg1 = alice.encrypt_message("Hello Bob from Alice with PFS")
    decrypted_bob = bob.decrypt_message(msg1)
    assert decrypted_bob.decode("utf-8") == "Hello Bob from Alice with PFS"

    # Alice sends message 2 (ratchet step)
    msg2 = alice.encrypt_message("Second confidential message")
    decrypted_bob_2 = bob.decrypt_message(msg2)
    assert decrypted_bob_2.decode("utf-8") == "Second confidential message"
