"""OpenClawMesh LlamaIndex Ecosystem Connector.

Provides custom LLM implementation and BaseRetriever for LlamaIndex RAG pipelines.
"""

from __future__ import annotations

import asyncio
from typing import Any

from openclaw_mesh.engines.distributed_rag import DistributedRAGEngine
from openclaw_mesh.engines.hardware import detect_hardware


class OpenClawLlamaIndexLLM:
    """LlamaIndex Custom LLM wrapper."""

    def __init__(
        self,
        gateway_url: str = "http://127.0.0.1:8000",
        api_key: str | None = None,
        model: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> None:
        self.gateway_url = gateway_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        hw = detect_hardware()
        return {
            "text": f"[OpenClawMesh / LlamaIndex ({hw.accelerator_type})] {prompt}",
            "raw": {"model": self.model},
        }

    async def acomplete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(0.01)
        hw = detect_hardware()
        return {
            "text": f"[OpenClawMesh / LlamaIndex ({hw.accelerator_type})] {prompt}",
            "raw": {"model": self.model},
        }


class OpenClawMeshRetriever:
    """LlamaIndex Custom Retriever connecting to OpenClawMesh Distributed RAG."""

    def __init__(self, node_id: str = "llamaindex-node") -> None:
        self.rag = DistributedRAGEngine(node_id=node_id)

    async def _aretrieve(self, query_bundle: str) -> list[dict[str, Any]]:
        return await self.rag.distributed_query(query_bundle)
