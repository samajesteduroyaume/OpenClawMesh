"""OpenClawMesh Connector for LangGraph & StateGraph Workflows.

Exposes LangGraph-compatible execution nodes for state-based multi-agent graphs.
"""

from __future__ import annotations

from typing import Any

from openclaw_mesh.client import MeshClient


class OpenClawGraphNode:
    """LangGraph runnable node backed by OpenClawMesh skill delegation."""

    def __init__(
        self,
        skill: str = "llm",
        state_key: str = "messages",
        output_key: str = "messages",
        model: str = "qwen2.5-coder-7b",
        mesh_client: MeshClient | None = None,
    ) -> None:
        self.skill = skill
        self.state_key = state_key
        self.output_key = output_key
        self.model = model
        self.client = mesh_client or MeshClient(name="langgraph-mesh-node")

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute graph node and update state dictionary."""
        input_val = state.get(self.state_key, "")
        if isinstance(input_val, list) and input_val:
            last = input_val[-1]
            prompt = last.get("content", str(last)) if isinstance(last, dict) else str(last)
        else:
            prompt = str(input_val)

        resp = await self.client.call_skill(
            skill=self.skill,
            payload={"prompt": prompt, "model": self.model},
        )
        out_text = ""
        if resp.get("ok"):
            res = resp.get("result", {})
            out_text = str(res.get("text", res.get("response", "")))

        new_state = dict(state)
        if isinstance(state.get(self.output_key), list):
            new_state[self.output_key] = list(state[self.output_key]) + [
                {"role": "assistant", "content": out_text}
            ]
        else:
            new_state[self.output_key] = out_text

        return new_state
