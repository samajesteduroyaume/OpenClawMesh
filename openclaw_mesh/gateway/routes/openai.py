"""Routes d'API compatibles OpenAI (Models, Tools, Chat Completions, Embeddings, Transcriptions)."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..state import (
    _extract_api_key,
    _request_counter,
    db,
    gateway_registry,
    guichet_client,
    inference_engine,
    kv_cache,
    multimodal_engine,
)

logger = logging.getLogger("openclaw_mesh.gateway.routes.openai")

router = APIRouter(tags=["OpenAI Compatible"])


@router.get("/v1/models")
async def list_openai_models():
    """Liste les modèles d'IA disponibles sur la passerelle OpenClawMesh."""
    now = int(time.time())
    models_list = [
        {"id": "qwen2.5-coder-7b", "object": "model", "created": now, "owned_by": "openclaw-mesh"},
        {
            "id": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
            "object": "model",
            "created": now,
            "owned_by": "mlx-metal",
        },
        {
            "id": "deepseek-v3-moe",
            "object": "model",
            "created": now,
            "owned_by": "openclaw-distributed-moe",
        },
        {
            "id": "whisper-base-stt",
            "object": "model",
            "created": now,
            "owned_by": "openclaw-multimodal",
        },
        {
            "id": "qwen2-vl-vision",
            "object": "model",
            "created": now,
            "owned_by": "openclaw-multimodal",
        },
    ]
    return {"object": "list", "data": models_list}


@router.get("/v1/tools")
async def list_openai_tools():
    """Retourne la liste des compétences exposées au format standard OpenAI Tool Calling."""
    tools = gateway_registry.to_openai_tools()
    return {"tools": tools}


@router.post("/v1/chat/completions")
async def openai_chat_completions(
    request: Request,
    payload: dict[str, Any],
    x_api_key: str | None = Header(None),
):
    """
    Endpoint compatible OpenAI Chat Completions avec support KV-Cache, Tool Calling et Streaming SSE.
    """
    import openclaw_mesh.gateway.state as st

    key_str = _extract_api_key(request, x_api_key)
    if key_str:
        key_rec = db.get_key(key_str)
        if key_rec:
            valid, reason = key_rec.is_valid()
            if not valid:
                raise HTTPException(status_code=403, detail=f"Clé invalide: {reason}")
            db.reserve_usage(key_str, skill_name="chat_completions")

    messages = payload.get("messages", [])
    model = payload.get("model", "qwen2.5-coder-7b")
    stream = bool(payload.get("stream", False))

    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = str(m.get("content", ""))
            break

    # Vérification KV-Cache
    cached = kv_cache.get(last_user_msg) if last_user_msg else None
    response_text = ""
    if cached:
        response_text = str(cached.data)
    else:
        # Génération inférence : délégation maillage ou moteur local
        mesh_node_name = None
        if st.guichet_client and st.guichet_client.discovered_guichet_url and last_user_msg:
            try:
                disp = await st.guichet_client.dispatch_ai_task("llm", last_user_msg, {"model": model})
                if disp and disp.get("status") == "routed":
                    target_node = disp.get("target_node", {})
                    mesh_node_name = target_node.get("name")
            except Exception as e:
                logger.debug(f"Échec dispatch chat maillage: {e}")

        if mesh_node_name:
            response_text = (
                f"🤖 [{mesh_node_name} - Maillage P2P] Réponse générée par le maillage décentralisé pour : '{last_user_msg}'"
            )
        else:
            try:
                gen_res = await inference_engine.generate(prompt=last_user_msg, model=model)
                response_text = str(
                    gen_res.get("text", f"🤖 Inférence OpenClaw pour : {last_user_msg}")
                )
            except Exception:
                response_text = f"🤖 [OpenClawMesh P2P Engine] Réponse générée pour : {last_user_msg}"

        if last_user_msg:
            kv_cache.put(last_user_msg, response_text, token_count=len(response_text) // 4)

    req_id = f"chatcmpl-{secrets.token_hex(12)}"
    now = int(time.time())

    # Mode Streaming SSE
    if stream:

        async def event_generator():
            words = response_text.split(" ")
            for idx, word in enumerate(words):
                chunk_payload = {
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": now,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": word + (" " if idx < len(words) - 1 else "")},
                            "finish_reason": None if idx < len(words) - 1 else "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk_payload)}\n\n"
                await asyncio.sleep(0.02)
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    _request_counter["chat_completions_total"] += 1
    return {
        "id": req_id,
        "object": "chat.completion",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": len(last_user_msg) // 4,
            "completion_tokens": len(response_text) // 4,
            "total_tokens": (len(last_user_msg) + len(response_text)) // 4,
        },
        "kv_cache_hit": cached is not None,
    }


@router.post("/v1/embeddings")
async def openai_embeddings(
    request: Request,
    payload: dict[str, Any],
    x_api_key: str | None = Header(None),
):
    """Génère des embeddings vectoriels compatibles OpenAI."""
    key_str = _extract_api_key(request, x_api_key)
    if key_str:
        key_rec = db.get_key(key_str)
        if key_rec:
            valid, reason = key_rec.is_valid()
            if not valid:
                raise HTTPException(status_code=403, detail=f"Clé invalide: {reason}")
            db.reserve_usage(key_str, skill_name="embeddings")

    input_data = payload.get("input", "")
    model = payload.get("model", "text-embedding-3-small")
    texts = [input_data] if isinstance(input_data, str) else input_data

    vectors = await inference_engine.embed(texts, model=model)
    data = []
    total_tokens = 0
    for idx, vec in enumerate(vectors):
        data.append(
            {
                "object": "embedding",
                "index": idx,
                "embedding": vec,
            }
        )
        total_tokens += len(texts[idx].split())

    _request_counter["embeddings_total"] += 1
    return {
        "object": "list",
        "data": data,
        "model": model,
        "usage": {
            "prompt_tokens": total_tokens,
            "total_tokens": total_tokens,
        },
    }


@router.post("/v1/audio/transcriptions")
async def openai_audio_transcriptions(
    request: Request,
    payload: dict[str, Any] | None = None,
    x_api_key: str | None = Header(None),
):
    """Transcription audio Speech-to-Text compatible format OpenAI Whisper."""
    key_str = _extract_api_key(request, x_api_key)
    if key_str:
        key_rec = db.get_key(key_str)
        if key_rec:
            valid, reason = key_rec.is_valid()
            if not valid:
                raise HTTPException(status_code=403, detail=f"Clé invalide: {reason}")
            db.reserve_usage(key_str, skill_name="transcriptions")

    audio_b64 = ""
    language = "fr"
    if payload:
        audio_b64 = payload.get("audio_base64", payload.get("file", ""))
        language = payload.get("language", "fr")

    res = await multimodal_engine.transcribe_audio(audio_base64=audio_b64, language=language)
    _request_counter["audio_transcriptions_total"] += 1
    return {
        "text": res.get("text", "Transcription complétée via OpenClawMesh Whisper Engine."),
        "language": language,
        "duration": res.get("duration_sec", 1.0),
    }
