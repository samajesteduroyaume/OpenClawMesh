"""Tests for P2P Federated Learning & LoRA Aggregation."""

from openclaw_mesh.engines.federated_lora import FederatedLoRAOrchestrator


def test_federated_lora_local_updates_and_aggregation():
    orchestrator = FederatedLoRAOrchestrator("qwen2.5-coder-7b", default_rank=4)
    layer = "model.layers.12.self_attn.q_proj"

    # Peer A generates local update with DP
    update_a = orchestrator.generate_local_update(
        node_id="peer-A",
        layer_name=layer,
        dim_in=32,
        dim_out=32,
        enable_dp=True,
    )
    assert update_a.rank == 4
    assert len(update_a.weights_matrix_a) == 32
    assert len(update_a.weights_matrix_b) == 4

    # Peer B generates local update with DP
    update_b = orchestrator.generate_local_update(
        node_id="peer-B",
        layer_name=layer,
        dim_in=32,
        dim_out=32,
        enable_dp=True,
    )

    # Perform FedAvg aggregation
    report = orchestrator.aggregate_updates(
        {
            "peer-A": [update_a],
            "peer-B": [update_b],
        }
    )

    assert report.round_id == 1
    assert report.participating_nodes == 2
    assert report.aggregated_layers_count == 1
    assert layer in orchestrator.global_adapters
    assert orchestrator.global_adapters[layer].rank == 4
