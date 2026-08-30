"""OpenClawMesh CRDT-Synchronized Distributed Vector Store.

Provides decentralized vector memory replication across peer nodes with
Conflict-Free Replicated Data Types (CRDT - LWW-Element-Set) and cosine semantic search.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class VectorDocument:
    """Document with vector embedding and CRDT timestamp metadata."""

    doc_id: str
    content: str
    vector: list[float]
    metadata: dict[str, Any]
    timestamp: float
    is_deleted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "vector": self.vector,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "is_deleted": self.is_deleted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VectorDocument:
        return cls(
            doc_id=data["doc_id"],
            content=data["content"],
            vector=data["vector"],
            metadata=data.get("metadata", {}),
            timestamp=float(data.get("timestamp", time.time())),
            is_deleted=bool(data.get("is_deleted", False)),
        )


class CRDTDistributedVectorStore:
    """CRDT-based LWW (Last-Write-Wins) Distributed Vector Store."""

    def __init__(self, node_id: str = "node-vector-local") -> None:
        self.node_id = node_id
        self._documents: dict[str, VectorDocument] = {}

    def insert(
        self,
        doc_id: str,
        content: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> VectorDocument:
        """Insert or update a document in the local store."""
        doc = VectorDocument(
            doc_id=doc_id,
            content=content,
            vector=vector,
            metadata=metadata or {},
            timestamp=time.time(),
            is_deleted=False,
        )
        self._documents[doc_id] = doc
        return doc

    def delete(self, doc_id: str) -> bool:
        """Mark document as deleted using a tombstone for CRDT sync."""
        if doc_id in self._documents:
            self._documents[doc_id].is_deleted = True
            self._documents[doc_id].timestamp = time.time()
            return True
        return False

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Compute cosine similarity between two float vectors."""
        if len(v1) != len(v2) or not v1:
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2, strict=False))
        norm1 = math.sqrt(sum(a * a for a in v1)) or 1.0
        norm2 = math.sqrt(sum(b * b for b in v2)) or 1.0
        return dot / (norm1 * norm2)

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Search active documents by vector similarity."""
        results: list[tuple[float, VectorDocument]] = []
        for doc in self._documents.values():
            if doc.is_deleted:
                continue
            sim = self.cosine_similarity(query_vector, doc.vector)
            results.append((sim, doc))

        # Sort descending
        results.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "doc_id": doc.doc_id,
                "content": doc.content,
                "similarity": round(sim, 4),
                "metadata": doc.metadata,
                "timestamp": doc.timestamp,
            }
            for sim, doc in results[:top_k]
        ]

    def get_sync_delta(self, since_timestamp: float = 0.0) -> list[dict[str, Any]]:
        """Generate replication delta for peer synchronization."""
        return [
            doc.to_dict() for doc in self._documents.values() if doc.timestamp > since_timestamp
        ]

    def merge_delta(self, delta_documents: list[dict[str, Any]]) -> int:
        """Merge remote documents with Last-Write-Wins conflict resolution."""
        merged_count = 0
        for raw in delta_documents:
            incoming = VectorDocument.from_dict(raw)
            existing = self._documents.get(incoming.doc_id)
            if existing is None or incoming.timestamp > existing.timestamp:
                self._documents[incoming.doc_id] = incoming
                merged_count += 1
        return merged_count

    def count(self) -> int:
        """Return total non-deleted documents."""
        return sum(1 for d in self._documents.values() if not d.is_deleted)
