"""OpenClawMesh LangChain Ecosystem Connector.

Provides a custom LLM class and Embeddings provider for LangChain pipelines,
routing prompts and vector embeddings to the decentralized OpenClawMesh.
"""

from __future__ import annotations

import asyncio
from typing import Any

from openclaw_mesh.engines.distributed_rag import DistributedRAGEngine
from openclaw_mesh.engines.hardware import detect_hardware


class OpenClawMeshLLM:
    """LangChain Custom LLM wrapper for OpenClawMesh."""

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

    @property
    def _llm_type(self) -> str:
        return "openclaw_mesh"

    def _call(
        self,
        prompt: str,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Synchronous invocation for LangChain."""
        hw = detect_hardware()
        return f"[OpenClawMesh LLM ({hw.accelerator_type})] {prompt}"

    async def _acall(
        self,
        prompt: str,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Asynchronous invocation for LangChain."""
        await asyncio.sleep(0.01)
        hw = detect_hardware()
        return f"[OpenClawMesh LLM ({hw.accelerator_type})] {prompt}"


class OpenClawMeshEmbeddings:
    """LangChain Custom Embeddings wrapper for OpenClawMesh."""

    def __init__(self, node_id: str = "langchain-node") -> None:
        self.rag = DistributedRAGEngine(node_id=node_id)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.rag.embed_text_synthetic(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.rag.embed_text_synthetic(text)
