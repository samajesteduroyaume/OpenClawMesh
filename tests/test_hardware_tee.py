"""Tests for Hardware TEE and Confidential Computing."""

from openclaw_mesh.security.hardware_tee import HardwareTEEProvider


def test_hardware_tee_quote_generation_and_verification():
    provider = HardwareTEEProvider()
    nonce = "challenge_nonce_98765"

    quote = provider.generate_attestation_quote(nonce)
    assert quote.nonce == nonce
    assert quote.pcr_digest
    assert quote.enclave_measurement
    assert quote.signature_b64

    # Verify quote with correct nonce
    valid, message = provider.verify_quote(quote, expected_nonce=nonce)
    assert valid is True
    assert "Verified Hardware TEE" in message


def test_hardware_tee_quote_wrong_nonce_fails():
    provider = HardwareTEEProvider()
    quote = provider.generate_attestation_quote("nonce_A")

    valid, message = provider.verify_quote(quote, expected_nonce="nonce_B")
    assert valid is False
    assert "mismatch" in message.lower()
