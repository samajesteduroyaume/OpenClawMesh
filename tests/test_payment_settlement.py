"""Tests for Decentralized Payment Settlement & Lightning Invoices."""

from openclaw_mesh.compute_economy import ComputeReceipt
from openclaw_mesh.payment_settlement import DecentralizedPaymentSettler


def test_payment_settlement_invoice_creation_and_settle():
    settler = DecentralizedPaymentSettler(default_rail="lightning")

    # Create two compute receipts
    r1 = ComputeReceipt(
        receipt_id="rec_01",
        consumer_node_id="client-node-A",
        provider_node_id="provider-node-B",
        model_name="qwen2.5-coder-7b",
        tokens_served=4000,
        duration_ms=250.0,
        credits_transferred=2.0,
    )
    r2 = ComputeReceipt(
        receipt_id="rec_02",
        consumer_node_id="client-node-A",
        provider_node_id="provider-node-B",
        model_name="deepseek-r1-8b",
        tokens_served=6000,
        duration_ms=350.0,
        credits_transferred=3.0,
    )

    # Batch settle into a single Lightning invoice
    invoice = settler.create_batch_settlement_invoice(
        receipts=[r1, r2],
        sats_per_credit=50,
        rail="lightning",
    )

    assert invoice.amount_sats == 250  # 5.0 credits * 50 sats
    assert invoice.rail == "lightning"
    assert invoice.receipt_count == 2
    assert invoice.status == "pending"
    assert invoice.payment_request_str.startswith("lnbc")

    # Settle the invoice
    settled, msg = settler.settle_invoice(invoice.invoice_id)
    assert settled is True
    assert "Settled 250 sats" in msg

    updated = settler.get_invoice(invoice.invoice_id)
    assert updated is not None
    assert updated.status == "settled"
