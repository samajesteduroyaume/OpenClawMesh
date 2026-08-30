"""OpenClawMesh TEE (Trusted Execution Environment) & Confidential Computing.

Simulates and interfaces with hardware-isolated enclaves (AMD SEV-SNP, Intel SGX,
Apple Secure Enclave), providing cryptographic attestation reports and isolated memory execution
so node operators cannot inspect or tamper with confidential prompts or inference weights.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from openclaw_mesh.crypto_e2ee import (
    derive_shared_key,
    generate_ephemeral_keypair,
)

logger = logging.getLogger("openclaw_mesh.security.tee")


class TEEType(str, Enum):
    AMD_SEV = "amd_sev_snp"
    INTEL_SGX = "intel_sgx"
    APPLE_SECURE_ENCLAVE = "apple_secure_enclave"
    VIRTUAL_EMULATED = "virtual_tee"


@dataclass
class AttestationReport:
    enclave_type: TEEType
    measurement_mrenclave: str  # Hash of code and initial state
    platform_version: str
    attestation_nonce: str
    enclave_public_key_b64: str
    signature: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enclave_type": self.enclave_type.value,
            "measurement_mrenclave": self.measurement_mrenclave,
            "platform_version": self.platform_version,
            "attestation_nonce": self.attestation_nonce,
            "enclave_public_key_b64": self.enclave_public_key_b64,
            "signature": self.signature,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttestationReport:
        return cls(
            enclave_type=TEEType(data["enclave_type"]),
            measurement_mrenclave=data["measurement_mrenclave"],
            platform_version=data["platform_version"],
            attestation_nonce=data["attestation_nonce"],
            enclave_public_key_b64=data["enclave_public_key_b64"],
            signature=data["signature"],
            timestamp=data.get("timestamp", time.time()),
        )


class ConfidentialEnclave:
    """Isolated compute environment inside a confidential execution boundary."""

    def __init__(
        self,
        node_id: str,
        enclave_type: TEEType = TEEType.VIRTUAL_EMULATED,
    ) -> None:
        self.node_id = node_id
        self.enclave_type = enclave_type
        self.priv_key, self.pub_key = generate_ephemeral_keypair()

        # Calculate synthetic MRENCLAVE measurement hash
        state_repr = f"{node_id}:{enclave_type.value}:openclaw_v1".encode()
        self.measurement = hashlib.sha256(state_repr).hexdigest()

    def generate_attestation_report(self, client_nonce: str) -> AttestationReport:
        """Produce a cryptographically signed hardware attestation quote."""
        report_payload = (
            f"{self.enclave_type.value}:{self.measurement}:{client_nonce}:{self.pub_key}"
        )
        sig = hashlib.sha256(f"{self.priv_key}:{report_payload}".encode()).hexdigest()

        return AttestationReport(
            enclave_type=self.enclave_type,
            measurement_mrenclave=self.measurement,
            platform_version="1.2.0-sec",
            attestation_nonce=client_nonce,
            enclave_public_key_b64=self.pub_key,
            signature=sig,
        )

    def execute_confidential_inference(
        self,
        encrypted_prompt_b64: str,
        client_ephemeral_pub_b64: str,
    ) -> dict[str, Any]:
        """Execute prompt inside isolated boundary and return confidential result."""
        # Decrypt inside enclave
        shared_key = derive_shared_key(self.priv_key, client_ephemeral_pub_b64)
        raw_data = base64.b64decode(encrypted_prompt_b64)
        nonce = raw_data[:12]
        ciphertext = raw_data[12:]

        chacha = ChaCha20Poly1305(shared_key)
        plain_prompt = chacha.decrypt(nonce, ciphertext, None).decode("utf-8")

        # Simulated isolated compute
        result_text = (
            f"[Enclave-Protected Output ({self.enclave_type.value})] Processed: {plain_prompt}"
        )

        # Re-encrypt inside enclave
        res_bytes = result_text.encode("utf-8")
        res_nonce = os.urandom(12)
        res_ciphertext = chacha.encrypt(res_nonce, res_bytes, None)
        packed_res = base64.b64encode(res_nonce + res_ciphertext).decode("utf-8")

        return {
            "status": "success",
            "enclave_measurement": self.measurement,
            "encrypted_result_b64": packed_res,
        }


class EnclaveVerifier:
    """Validates remote node TEE attestation quotes before dispatching sensitive compute."""

    @staticmethod
    def verify_attestation(report: AttestationReport, expected_nonce: str) -> bool:
        """Verify the validity and fresh nonce of an attestation quote."""
        if report.attestation_nonce != expected_nonce:
            logger.warning("Attestation verification failed: nonce mismatch")
            return False

        if not report.enclave_public_key_b64 or not report.measurement_mrenclave:
            return False

        # Freshness check (within 5 minutes)
        if abs(time.time() - report.timestamp) > 300.0:
            logger.warning("Attestation report expired")
            return False

        return True
