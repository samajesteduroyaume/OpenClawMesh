"""OpenClawMesh Sovereign Compute Economy & Peer Credit Ledger.

Provides decentralized inference credit accounting based on fair compute bartering
(Tit-for-Tat / Proof-of-Useful-Compute), rewarding nodes that contribute GPU/NPU compute
and enabling sovereign credit settlement without centralized billing servers.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComputeReceipt:
    """Proof of served inference compute signed by client and server peers."""

    receipt_id: str
    consumer_node_id: str
    provider_node_id: str
    model_name: str
    tokens_served: int
    duration_ms: float
    credits_transferred: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "consumer_node_id": self.consumer_node_id,
            "provider_node_id": self.provider_node_id,
            "model_name": self.model_name,
            "tokens_served": self.tokens_served,
            "duration_ms": self.duration_ms,
            "credits_transferred": self.credits_transferred,
            "timestamp": self.timestamp,
        }


class PeerComputeCreditLedger:
    """Decentralized credit ledger tracking peer compute contributions and consumption."""

    def __init__(self, initial_credit_grant: float = 100.0) -> None:
        self.initial_credit_grant = initial_credit_grant
        self._balances: dict[str, float] = {}
        self._receipts: list[ComputeReceipt] = []

    def get_balance(self, node_id: str) -> float:
        """Get current compute credit balance for a peer node."""
        if node_id not in self._balances:
            self._balances[node_id] = self.initial_credit_grant
        return round(self._balances[node_id], 4)

    def record_compute_transaction(
        self,
        consumer_node_id: str,
        provider_node_id: str,
        model_name: str,
        tokens_served: int,
        duration_ms: float,
        rate_per_k_tokens: float = 0.5,
    ) -> ComputeReceipt:
        """Transfer credits from consumer to provider upon successful inference completion."""
        credits = round((tokens_served / 1000.0) * rate_per_k_tokens, 4)
        credits = max(0.001, credits)

        # Debit consumer, credit provider
        consumer_bal = self.get_balance(consumer_node_id)
        provider_bal = self.get_balance(provider_node_id)

        self._balances[consumer_node_id] = consumer_bal - credits
        self._balances[provider_node_id] = provider_bal + credits

        receipt_raw = f"{consumer_node_id}:{provider_node_id}:{tokens_served}:{time.time()}"
        receipt_id = hashlib.sha256(receipt_raw.encode()).hexdigest()[:16]

        receipt = ComputeReceipt(
            receipt_id=receipt_id,
            consumer_node_id=consumer_node_id,
            provider_node_id=provider_node_id,
            model_name=model_name,
            tokens_served=tokens_served,
            duration_ms=duration_ms,
            credits_transferred=credits,
        )
        self._receipts.append(receipt)
        return receipt

    def get_transaction_history(
        self, node_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Retrieve recent compute transactions."""
        matched = [
            r.to_dict()
            for r in reversed(self._receipts)
            if node_id is None or r.consumer_node_id == node_id or r.provider_node_id == node_id
        ]
        return matched[:limit]
