"""Tests for Proof-of-Inference (PoI) Verifier."""

from openclaw_mesh.security.proof_of_inference import ProofOfInferenceVerifier


def test_poi_create_and_verify_success():
    verifier = ProofOfInferenceVerifier()
    node_id = "node-gpu-42"
    prompt = "Quelle est la capitale de la France ?"
    output_text = "La capitale de la France est Paris, une métropole européenne majeure."

    attestation = verifier.create_attestation(
        node_id=node_id,
        prompt=prompt,
        output_text=output_text,
    )

    valid, reason = verifier.verify_inference(
        attestation=attestation,
        prompt=prompt,
        output_text=output_text,
    )
    assert valid is True
    assert "Valid" in reason


def test_poi_tampered_output_fails_and_slashes():
    verifier = ProofOfInferenceVerifier()
    node_id = "node-dishonest-99"
    prompt = "Calculer 2 + 2"
    output_text = "4"

    attestation = verifier.create_attestation(
        node_id=node_id,
        prompt=prompt,
        output_text=output_text,
    )

    # Tamper with returned output
    valid, reason = verifier.verify_inference(
        attestation=attestation,
        prompt=prompt,
        output_text="5 (tampered response)",
    )
    assert valid is False
    assert "mismatch" in reason.lower()

    # Check peer reputation was slashed
    rec = verifier.reputation_mgr.get_record(node_id)
    assert rec.score < 0.6
    assert rec.dispute_count >= 1


def test_poi_low_entropy_spam_fails():
    verifier = ProofOfInferenceVerifier()
    node_id = "node-spammer-1"
    prompt = "Explain quantum mechanics"
    output_text = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    attestation = verifier.create_attestation(
        node_id=node_id,
        prompt=prompt,
        output_text=output_text,
    )

    valid, reason = verifier.verify_inference(
        attestation=attestation,
        prompt=prompt,
        output_text=output_text,
    )
    assert valid is False
    assert "entropy" in reason.lower()
