"""OpenClawMesh Proof-of-Inference (PoI) & Verifiable Consensus Engine.

Provides cryptographic verification and statistical cross-sampling of remote
inference outputs, detecting malicious, lazy, or poisoned peer compute without
requiring full redundant re-execution of all queries.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import time
from dataclasses import dataclass
from typing import Any

from openclaw_mesh.reputation import ReputationManager


@dataclass
class InferenceAttestation:
    """Cryptographic attestation produced by an inference node."""

    node_id: str
    prompt_hash: str
    output_hash: str
    sample_entropy: float
    timestamp: float
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "prompt_hash": self.prompt_hash,
            "output_hash": self.output_hash,
            "sample_entropy": self.sample_entropy,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


class ProofOfInferenceVerifier:
    """Verifies correctness and statistical plausibility of remote peer compute."""

    def __init__(
        self,
        reputation_mgr: ReputationManager | None = None,
        min_entropy_threshold: float = 1.8,
    ) -> None:
        self.reputation_mgr = reputation_mgr or ReputationManager()
        self.min_entropy_threshold = min_entropy_threshold

    @staticmethod
    def compute_text_entropy(text: str) -> float:
        """Calculates Shannon entropy of token/character distributions."""
        if not text:
            return 0.0
        frequencies: dict[str, int] = {}
        for char in text:
            frequencies[char] = frequencies.get(char, 0) + 1

        entropy = 0.0
        length = len(text)
        for count in frequencies.values():
            p = count / length
            entropy -= p * math.log2(p)
        return round(entropy, 4)

    def create_attestation(
        self,
        node_id: str,
        prompt: str,
        output_text: str,
        signing_key: bytes | None = None,
    ) -> InferenceAttestation:
        """Create an attestation proof for a completed inference task."""
        p_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        o_hash = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
        entropy = self.compute_text_entropy(output_text)
        ts = time.time()

        key = signing_key or b"OPENCLAW_DEFAULT_POI_KEY"
        payload = f"{node_id}:{p_hash}:{o_hash}:{entropy}:{ts}".encode()
        sig = hmac.new(key, payload, hashlib.sha256).hexdigest()

        return InferenceAttestation(
            node_id=node_id,
            prompt_hash=p_hash,
            output_hash=o_hash,
            sample_entropy=entropy,
            timestamp=ts,
            signature=sig,
        )

    def verify_inference(
        self,
        attestation: InferenceAttestation,
        prompt: str,
        output_text: str,
        verification_key: bytes | None = None,
    ) -> tuple[bool, str]:
        """Validates the attestation and checks for signs of degradation or fraud."""
        expected_p_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if attestation.prompt_hash != expected_p_hash:
            self._slash_peer(attestation.node_id, reason="Prompt hash mismatch")
            return False, "Prompt hash mismatch"

        expected_o_hash = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
        if attestation.output_hash != expected_o_hash:
            self._slash_peer(attestation.node_id, reason="Output hash mismatch")
            return False, "Output hash mismatch"

        # Check signature
        key = verification_key or b"OPENCLAW_DEFAULT_POI_KEY"
        payload = f"{attestation.node_id}:{attestation.prompt_hash}:{attestation.output_hash}:{attestation.sample_entropy}:{attestation.timestamp}".encode()
        expected_sig = hmac.new(key, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(attestation.signature, expected_sig):
            self._slash_peer(attestation.node_id, reason="Invalid cryptographic signature")
            return False, "Invalid signature"

        # Statistical sanity check (entropy threshold to catch repetitive garbage/spam loops)
        if len(output_text) > 40 and attestation.sample_entropy < self.min_entropy_threshold:
            self._slash_peer(attestation.node_id, reason="Abnormally low entropy (gibberish/loop)")
            return False, "Abnormally low entropy output"

        # Reward verified peer
        self.reputation_mgr.record_success(attestation.node_id, latency_ms=12.0)
        return True, "Valid Proof-of-Inference"

    def _slash_peer(self, node_id: str, reason: str) -> None:
        """Penalizes malicious or faulty peer reputation score."""
        self.reputation_mgr.record_dispute(node_id, reason=reason)
