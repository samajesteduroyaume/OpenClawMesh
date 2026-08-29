import pytest

from openclaw_mesh.connectors.langchain import OpenClawMeshEmbeddings, OpenClawMeshLLM
from openclaw_mesh.connectors.llamaindex import OpenClawLlamaIndexLLM, OpenClawMeshRetriever
from openclaw_mesh.mcp_server import OpenClawMCPServer


@pytest.mark.asyncio
async def test_mcp_server_protocol():
    server = OpenClawMCPServer()

    # 1. Initialize
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    init_res = await server.handle_request(init_req)
    assert init_res["result"]["serverInfo"]["name"] == "OpenClawMesh-MCP"

    # 2. List tools
    tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    tools_res = await server.handle_request(tools_req)
    tool_names = [t["name"] for t in tools_res["result"]["tools"]]
    assert "mesh_status" in tool_names
    assert "mesh_inference" in tool_names
    assert "mesh_memory_query" in tool_names

    # 3. Call tool
    call_req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "mesh_inference",
            "arguments": {"prompt": "Write a quick test function"},
        },
    }
    call_res = await server.handle_request(call_req)
    assert not call_res["result"]["isError"]
    assert "OpenClawMesh" in call_res["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_langchain_and_llamaindex_connectors():
    # LangChain LLM & Embeddings
    lc_llm = OpenClawMeshLLM()
    resp = await lc_llm._acall("Hello from LangChain")
    assert "OpenClawMesh LLM" in resp

    lc_emb = OpenClawMeshEmbeddings()
    embs = lc_emb.embed_documents(["document 1", "document 2"])
    assert len(embs) == 2
    assert len(embs[0]) == 64

    # LlamaIndex LLM & Retriever
    li_llm = OpenClawLlamaIndexLLM()
    li_resp = await li_llm.acomplete("Hello from LlamaIndex")
    assert "LlamaIndex" in li_resp["text"]

    li_retriever = OpenClawMeshRetriever()
    results = await li_retriever._aretrieve("Querying memory")
    assert isinstance(results, list)
