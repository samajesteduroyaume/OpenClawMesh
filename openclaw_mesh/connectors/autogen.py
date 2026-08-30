"""OpenClawMesh Connector for Microsoft AutoGen Framework.

Provides an AutoGen ModelClient interface to route multi-agent conversations
through the decentralized P2P OpenClaw mesh.
"""

from __future__ import annotations

import time
from typing import Any

from openclaw_mesh.client import MeshClient


class OpenClawAutoGenClient:
    """AutoGen ModelClient implementation for OpenClawMesh."""

    def __init__(
        self,
        model: str = "qwen2.5-coder-7b",
        mesh_client: MeshClient | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.client = mesh_client or MeshClient(name="autogen-mesh-client")
        self.config = config or {}

    async def create(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create completions matching AutoGen client protocol."""
        messages = params.get("messages", [])
        last_msg = messages[-1].get("content", "") if messages else ""
        t0 = time.perf_counter()

        resp = await self.client.call_skill(
            skill="llm",
            payload={"prompt": last_msg, "model": self.model},
        )
        duration_s = time.perf_counter() - t0
        text = ""
        if resp.get("ok"):
            res = resp.get("result", {})
            text = str(res.get("text", res.get("response", "")))

        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "model": self.model,
            "usage": {
                "prompt_tokens": len(last_msg.split()),
                "completion_tokens": len(text.split()),
                "total_tokens": len(last_msg.split()) + len(text.split()),
            },
            "cost": 0.0,  # OpenClawMesh is 100% Free & Sovereign
            "duration": duration_s,
        }

    def message_retrieval(self, response: dict[str, Any]) -> list[str]:
        """Extract text responses from AutoGen completion result."""
        return [choice["message"]["content"] for choice in response.get("choices", [])]
