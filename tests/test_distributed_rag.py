import pytest

from openclaw_mesh.engines.distributed_rag import (
    DistributedRAGEngine,
    cosine_similarity,
)


def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]

    assert round(cosine_similarity(v1, v2), 4) == 1.0
    assert round(cosine_similarity(v1, v3), 4) == 0.0


@pytest.mark.asyncio
async def test_distributed_rag_index_and_query():
    rag = DistributedRAGEngine(node_id="node-rag-1")

    doc1 = rag.index_document(
        "OpenClawMesh is a decentralized AI protocol", metadata={"topic": "p2p"}
    )
    doc2 = rag.index_document(
        "Baking bread requires flour, yeast, and water", metadata={"topic": "cooking"}
    )

    assert doc1.doc_id is not None
    assert doc2.doc_id is not None
    assert rag.local_index.size() == 2

    # Query
    results = await rag.distributed_query(
        "Tell me about decentralized AI protocol", top_k=2, remote_peers=["peer-remote"]
    )
    assert len(results) >= 2
    # Local doc1 should be top or prominent
    sources = [r["source"] for r in results]
    assert "local" in sources
    assert "remote_p2p" in sources
