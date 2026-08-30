"""Tests for CRDT-Synchronized Distributed Vector Store."""

from openclaw_mesh.engines.distributed_vector_store import CRDTDistributedVectorStore


def test_crdt_vector_store_operations_and_search():
    store = CRDTDistributedVectorStore("node-1")
    store.insert("doc-1", "Introduction au réseau mesh souverain", [1.0, 0.0, 0.0])
    store.insert("doc-2", "Guide d'accélération GPU Metal MLX", [0.0, 1.0, 0.0])
    store.insert("doc-3", "Cryptographie post-quantique Kyber", [0.0, 0.0, 1.0])

    assert store.count() == 3

    # Search for GPU related doc
    results = store.search([0.1, 0.9, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0]["doc_id"] == "doc-2"
    assert results[0]["similarity"] > 0.8


def test_crdt_vector_store_replication_and_tombstones():
    node_a = CRDTDistributedVectorStore("node-A")
    node_b = CRDTDistributedVectorStore("node-B")

    node_a.insert("doc-1", "Contenu créé sur le nœud A", [0.5, 0.5, 0.0])
    delta_a = node_a.get_sync_delta()

    # Replicate delta to node B
    merged = node_b.merge_delta(delta_a)
    assert merged == 1
    assert node_b.count() == 1

    # Node A deletes doc-1 with tombstone
    node_a.delete("doc-1")
    delta_a_deleted = node_a.get_sync_delta()

    # Replicate deletion to node B
    node_b.merge_delta(delta_a_deleted)
    assert node_b.count() == 0
