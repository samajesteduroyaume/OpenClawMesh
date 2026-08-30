"""Tests for Extended Multi-Agent Framework Connectors (CrewAI, AutoGen, LangGraph)."""

from unittest.mock import AsyncMock

import pytest

from openclaw_mesh.client import MeshClient
from openclaw_mesh.connectors.autogen import OpenClawAutoGenClient
from openclaw_mesh.connectors.crewai import OpenClawCrewAILLM
from openclaw_mesh.connectors.langgraph import OpenClawGraphNode


@pytest.mark.asyncio
async def test_crewai_connector():
    mock_client = MeshClient(name="test-client")
    mock_client.call_skill = AsyncMock(
        return_value={"ok": True, "result": {"text": "CrewAI Mesh Result"}}
    )

    llm = OpenClawCrewAILLM(model="qwen2.5-coder-7b", mesh_client=mock_client)
    res = await llm.a_call("Test task for crew agent")
    assert res == "CrewAI Mesh Result"
    mock_client.call_skill.assert_awaited_once()


@pytest.mark.asyncio
async def test_autogen_connector():
    mock_client = MeshClient(name="test-client")
    mock_client.call_skill = AsyncMock(
        return_value={"ok": True, "result": {"text": "AutoGen Mesh Result"}}
    )

    client = OpenClawAutoGenClient(model="qwen2.5-coder-7b", mesh_client=mock_client)
    response = await client.create({"messages": [{"role": "user", "content": "Hello AutoGen"}]})
    assert response["choices"][0]["message"]["content"] == "AutoGen Mesh Result"
    assert response["cost"] == 0.0

    retrieved = client.message_retrieval(response)
    assert retrieved == ["AutoGen Mesh Result"]


@pytest.mark.asyncio
async def test_langgraph_connector():
    mock_client = MeshClient(name="test-client")
    mock_client.call_skill = AsyncMock(
        return_value={"ok": True, "result": {"text": "Graph Node Output"}}
    )

    node = OpenClawGraphNode(
        skill="llm", state_key="messages", output_key="messages", mesh_client=mock_client
    )
    state = {"messages": [{"role": "user", "content": "Initial Graph State"}]}
    new_state = await node(state)
    assert len(new_state["messages"]) == 2
    assert new_state["messages"][-1]["content"] == "Graph Node Output"
