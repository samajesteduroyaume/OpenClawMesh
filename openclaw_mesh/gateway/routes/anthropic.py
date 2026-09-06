"""Routes d'API compatibles Anthropic Messages (/v1/messages)."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..state import (
    _extract_api_key,
    _request_counter,
    db,
    inference_engine,
    kv_cache,
)

logger = logging.getLogger("openclaw_mesh.gateway.routes.anthropic")

router = APIRouter(tags=["Anthropic Compatible"])


@router.post("/v1/messages")
async def anthropic_messages(
    request: Request,
    payload: dict[str, Any],
    x_api_key: str | None = Header(None),
    x_anthropic_version: str | None = Header(None, alias="anthropic-version"),
):
    """Endpoint standard compatible avec l'API Anthropic Claude (/v1/messages)."""
    key_str = _extract_api_key(request, x_api_key)
    if key_str:
        key_rec = db.get_key(key_str)
        if key_rec:
            valid, reason = key_rec.is_valid()
            if not valid:
                raise HTTPException(status_code=403, detail=f"Clé invalide: {reason}")
            db.reserve_usage(key_str, skill_name="anthropic_messages")

    messages = payload.get("messages", [])
    model = payload.get("model", "claude-3-5-sonnet-20241022")
    stream = bool(payload.get("stream", False))

    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, list):
                last_user_msg = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            else:
                last_user_msg = str(content)
            break

    # Exécution ou cache
    cached = kv_cache.get(last_user_msg) if last_user_msg else None
    if cached:
        response_text = str(cached.data)
    else:
        try:
            gen_res = await inference_engine.generate(prompt=last_user_msg, model=model)
            response_text = str(
                gen_res.get("text", f"🤖 Inférence OpenClaw pour : {last_user_msg}")
            )
        except Exception:
            response_text = (
                f"🤖 [OpenClawMesh Claude Adapter] Réponse générée pour : {last_user_msg}"
            )
        if last_user_msg:
            kv_cache.put(last_user_msg, response_text, token_count=len(response_text) // 4)

    msg_id = f"msg_{secrets.token_hex(12)}"

    if stream:

        async def anthropic_stream():
            yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'model': model, 'usage': {'input_tokens': len(last_user_msg) // 4, 'output_tokens': 1}}})}\n\n"
            words = response_text.split(" ")
            for word in words:
                yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': word + ' '}})}\n\n"
                await asyncio.sleep(0.015)
            yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

        return StreamingResponse(anthropic_stream(), media_type="text/event-stream")

    _request_counter["anthropic_total"] += 1
    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [
            {
                "type": "text",
                "text": response_text,
            }
        ],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": len(last_user_msg) // 4,
            "output_tokens": len(response_text) // 4,
        },
    }
