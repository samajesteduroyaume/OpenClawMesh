import json
import time

import pytest

from openclaw_mesh.protocol import (
    TaskChunk,
    TaskRequest,
    TaskResponse,
    parse_message,
)


def test_task_request_serialization():
    req = TaskRequest(
        skill="llm",
        payload={"prompt": "test prompt", "temperature": 0.5},
        origin="openclaw-1",
    )
    json_str = req.to_json()
    data = json.loads(json_str)

    assert data["type"] == "task_request"
    assert data["skill"] == "llm"
    assert data["payload"]["prompt"] == "test prompt"
    assert data["origin"] == "openclaw-1"

    rebuilt = TaskRequest.from_dict(data)
    assert rebuilt.skill == req.skill
    assert rebuilt.request_id == req.request_id
    assert rebuilt.payload == req.payload


def test_task_chunk_serialization():
    chunk = TaskChunk(request_id="abc12345", index=3, chunk={"text": "hello"})
    data = chunk.to_dict()
    assert data["type"] == "task_chunk"
    assert data["request_id"] == "abc12345"
    assert data["index"] == 3
    assert data["chunk"] == {"text": "hello"}

    rebuilt = TaskChunk.from_dict(data)
    assert rebuilt.request_id == "abc12345"
    assert rebuilt.index == 3
    assert rebuilt.chunk == {"text": "hello"}


def test_task_response_serialization():
    resp = TaskResponse(
        request_id="abc12345",
        ok=True,
        result={"summary": "ok"},
        handled_by="node-1",
        streamed=False,
    )
    json_str = resp.to_json()
    data = parse_message(json_str)
    assert data["type"] == "task_response"
    assert data["ok"] is True
    assert data["result"] == {"summary": "ok"}
    assert data["handled_by"] == "node-1"

    rebuilt = TaskResponse.from_dict(data)
    assert rebuilt.ok is True
    assert rebuilt.handled_by == "node-1"


def test_hmac_signing_and_verification():
    psk = "super_secret_mesh_key_123"
    req = TaskRequest(
        skill="echo",
        payload={"msg": "hello", "nested": {"k": "v"}},
        origin="agent-test",
    )

    # Sign request
    req.sign(psk)
    assert req.sig is not None

    # Verify with correct PSK
    assert req.verify(psk) is True

    # Verify with wrong PSK
    assert req.verify("wrong_key") is False

    # Tampered payload should fail verification
    req.payload["msg"] = "tampered"
    assert req.verify(psk) is False


def test_protocol_rejects_non_object_and_invalid_task_request():
    with pytest.raises(ValueError, match="objet"):
        parse_message("[]")
    with pytest.raises(ValueError, match="Payload invalide"):
        TaskRequest.from_dict(
            {
                "type": "task_request",
                "skill": "echo",
                "payload": [],
                "request_id": "request-1",
                "origin": "tester",
                "ts": time.time(),
            }
        )
