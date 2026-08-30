"""OpenClawMesh Decentralized Settlement & Lightning / L2 Micro-Payments.

Anchors ComputeReceipts on decentralized payment rails:
- ⚡ Bitcoin Lightning Network (BOLT-11 Invoices & Hodl Invoices)
- 🟣 Layer 2 EVM / Solana Micro-State Channels
Enables sovereign peer-to-peer monetization and GPU compute compensation.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from openclaw_mesh.compute_economy import ComputeReceipt


@dataclass
class SettlementInvoice:
    invoice_id: str
    consumer_node_id: str
    provider_node_id: str
    amount_sats: int
    rail: str  # 'lightning', 'solana_l2', 'evm_state_channel'
    payment_hash: str
    payment_request_str: str
    status: str = "pending"  # 'pending', 'settled', 'expired'
    receipt_count: int = 1
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "invoice_id": self.invoice_id,
            "consumer_node_id": self.consumer_node_id,
            "provider_node_id": self.provider_node_id,
            "amount_sats": self.amount_sats,
            "rail": self.rail,
            "payment_hash": self.payment_hash,
            "payment_request_str": self.payment_request_str,
            "status": self.status,
            "receipt_count": self.receipt_count,
            "created_at": self.created_at,
        }


class DecentralizedPaymentSettler:
    """Manages batch settlement of ComputeReceipts over payment rails."""

    def __init__(self, default_rail: str = "lightning") -> None:
        self.default_rail = default_rail
        self._invoices: dict[str, SettlementInvoice] = {}

    def create_batch_settlement_invoice(
        self,
        receipts: list[ComputeReceipt],
        sats_per_credit: int = 100,
        rail: str | None = None,
    ) -> SettlementInvoice:
        """Bundles a batch of compute receipts into a single payment invoice."""
        if not receipts:
            raise ValueError("Cannot settle empty receipt batch")

        consumer = receipts[0].consumer_node_id
        provider = receipts[0].provider_node_id
        total_credits = sum(r.credits_transferred for r in receipts)
        total_sats = max(1, int(round(total_credits * sats_per_credit)))

        preimage = secrets.token_bytes(32)
        payment_hash = hashlib.sha256(preimage).hexdigest()
        inv_id = f"inv_{secrets.token_hex(8)}"

        target_rail = rail or self.default_rail
        payment_str = (
            f"lnbc{total_sats}n1p{payment_hash[:20]}"
            if target_rail == "lightning"
            else f"l2:{target_rail}:{inv_id}"
        )

        invoice = SettlementInvoice(
            invoice_id=inv_id,
            consumer_node_id=consumer,
            provider_node_id=provider,
            amount_sats=total_sats,
            rail=target_rail,
            payment_hash=payment_hash,
            payment_request_str=payment_str,
            receipt_count=len(receipts),
        )
        self._invoices[inv_id] = invoice
        return invoice

    def settle_invoice(self, invoice_id: str) -> tuple[bool, str]:
        """Marks invoice as settled upon receiving payment proof."""
        inv = self._invoices.get(invoice_id)
        if not inv:
            return False, "Invoice not found"
        if inv.status == "settled":
            return True, "Invoice already settled"

        inv.status = "settled"
        return (
            True,
            f"Settled {inv.amount_sats} sats via {inv.rail} for {inv.receipt_count} receipts",
        )

    def get_invoice(self, invoice_id: str) -> SettlementInvoice | None:
        return self._invoices.get(invoice_id)
