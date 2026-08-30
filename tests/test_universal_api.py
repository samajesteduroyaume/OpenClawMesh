import pytest
from fastapi.testclient import TestClient

from openclaw_mesh.gateway.server import app

client = TestClient(app)


@pytest.fixture
def auth_headers():
    resp = client.post(
        "/api/v1/auth/free-key", json={"email": "tester@openclaw.ai", "plan": "free_community"}
    )
    assert resp.status_code == 200
    key = resp.json()["api_key"]
    return {"Authorization": f"Bearer {key}", "X-API-Key": key}


def test_openai_embeddings_endpoint(auth_headers):
    resp = client.post(
        "/v1/embeddings",
        json={"input": "Test query for vector embedding", "model": "text-embedding-3-small"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 1
    assert len(data["data"][0]["embedding"]) > 0


def test_openai_audio_transcriptions_endpoint(auth_headers):
    resp = client.post(
        "/v1/audio/transcriptions",
        json={
            "audio_base64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=",
            "language": "fr",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data
    assert data["language"] == "fr"


def test_anthropic_messages_endpoint(auth_headers):
    resp = client.post(
        "/v1/messages",
        json={
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "Hello Claude adapter!"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert len(data["content"]) > 0


def test_ollama_endpoints():
    # 1. Version
    v_resp = client.get("/api/version")
    assert v_resp.status_code == 200
    assert "version" in v_resp.json()

    # 2. Tags
    t_resp = client.get("/api/tags")
    assert t_resp.status_code == 200
    assert len(t_resp.json()["models"]) >= 3

    # 3. Generate
    g_resp = client.post(
        "/api/generate",
        json={"model": "qwen2.5-coder:7b", "prompt": "Hello Ollama", "stream": False},
    )
    assert g_resp.status_code == 200
    assert "response" in g_resp.json()

    # 4. Chat
    c_resp = client.post(
        "/api/chat",
        json={
            "model": "qwen2.5-coder:7b",
            "messages": [{"role": "user", "content": "Hello Ollama Chat"}],
            "stream": False,
        },
    )
    assert c_resp.status_code == 200
    assert "message" in c_resp.json()


def test_mcp_messages_endpoint():
    resp = client.post(
        "/mcp/messages",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert "result" in data
    assert "tools" in data["result"]
    tool_names = [t["name"] for t in data["result"]["tools"]]
    assert "mesh_status" in tool_names
    assert "mesh_inference" in tool_names
