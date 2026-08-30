"""OpenClawMesh Connector for CrewAI Multi-Agent Framework.

Enables seamless execution of CrewAI tasks and agents through decentralized mesh nodes,
leveraging local/remote GPU compute and peer skills.
"""

from __future__ import annotations

import asyncio
from typing import Any

from openclaw_mesh.client import MeshClient


class OpenClawCrewAILLM:
    """CrewAI-compatible LLM provider backed by OpenClawMesh."""

    def __init__(
        self,
        model: str = "qwen2.5-coder-7b",
        temperature: float = 0.3,
        max_tokens: int = 512,
        peer_name: str | None = None,
        mesh_client: MeshClient | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.peer_name = peer_name
        self.client = mesh_client or MeshClient(name="crewai-mesh-agent")

    async def a_call(self, prompt: str, **kwargs: Any) -> str:
        """Asynchronous prompt invocation over the mesh."""
        payload = {
            "prompt": prompt,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        resp = await self.client.call_skill(
            skill="llm",
            payload=payload,
            peer_name=self.peer_name,
        )
        if resp.get("ok"):
            res = resp.get("result", {})
            return str(res.get("text", res.get("response", "")))
        raise RuntimeError(f"OpenClawMesh CrewAI execution failed: {resp.get('error')}")

    def call(self, prompt: str, **kwargs: Any) -> str:
        """Synchronous wrapper for CrewAI execution loop."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(lambda: asyncio.run(self.a_call(prompt, **kwargs))).result()
            return loop.run_until_complete(self.a_call(prompt, **kwargs))
        except Exception:
            return asyncio.run(self.a_call(prompt, **kwargs))
