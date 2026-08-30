from openclaw_mesh.compute_economy import PeerComputeCreditLedger


def test_peer_credit_ledger_transactions():
    ledger = PeerComputeCreditLedger(initial_credit_grant=100.0)
    consumer = "client-agent-1"
    provider = "gpu-node-h100"

    assert ledger.get_balance(consumer) == 100.0
    assert ledger.get_balance(provider) == 100.0

    # Record compute transaction for 2000 tokens
    receipt = ledger.record_compute_transaction(
        consumer_node_id=consumer,
        provider_node_id=provider,
        model_name="deepseek-r1-distill-8b",
        tokens_served=2000,
        duration_ms=120.0,
        rate_per_k_tokens=0.5,
    )

    assert receipt.tokens_served == 2000
    assert receipt.credits_transferred == 1.0  # (2000/1000) * 0.5
    assert receipt.receipt_id

    # Verify updated balances
    assert ledger.get_balance(consumer) == 99.0
    assert ledger.get_balance(provider) == 101.0

    # History retrieval
    history = ledger.get_transaction_history(consumer)
    assert len(history) == 1
    assert history[0]["consumer_node_id"] == consumer
