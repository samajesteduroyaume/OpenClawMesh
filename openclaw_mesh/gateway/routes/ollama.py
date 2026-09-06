"""Routes d'API compatibles Ollama (/api/generate, /api/chat, /api/tags, /api/version)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..state import inference_engine

logger = logging.getLogger("openclaw_mesh.gateway.routes.ollama")

router = APIRouter(tags=["Ollama Compatible"])


@router.get("/api/version")
async def ollama_version():
    return {"version": "0.5.4-openclaw-mesh"}


@router.get("/api/tags")
async def ollama_tags():
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "models": [
            {
                "name": "qwen2.5-coder:7b",
                "model": "qwen2.5-coder:7b",
                "modified_at": now_iso,
                "size": 4700000000,
                "digest": "sha256:openclawqwen25coder7bdigest",
                "details": {
                    "format": "gguf",
                    "family": "qwen2",
                    "parameter_size": "7B",
                    "quantization_level": "Q4_K_M",
                },
            },
            {
                "name": "llama3.2:3b",
                "model": "llama3.2:3b",
                "modified_at": now_iso,
                "size": 2200000000,
                "digest": "sha256:openclawllama323bdigest",
                "details": {
                    "format": "gguf",
                    "family": "llama",
                    "parameter_size": "3B",
                    "quantization_level": "Q4_K_M",
                },
            },
            {
                "name": "deepseek-r1:8b",
                "model": "deepseek-r1:8b",
                "modified_at": now_iso,
                "size": 4900000000,
                "digest": "sha256:openclawdeepseekr18bdigest",
                "details": {
                    "format": "gguf",
                    "family": "deepseek",
                    "parameter_size": "8B",
                    "quantization_level": "Q4_K_M",
                },
            },
        ]
    }


@router.post("/api/generate")
async def ollama_generate(payload: dict[str, Any]):
    prompt = payload.get("prompt", "")
    model = payload.get("model", "qwen2.5-coder:7b")
    stream = bool(payload.get("stream", False))

    try:
        gen_res = await inference_engine.generate(prompt=prompt, model=model)
        text = str(gen_res.get("text", f"Ollama mesh output for {prompt}"))
    except Exception:
        text = f"Ollama mesh output for {prompt}"

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if stream:

        async def ollama_stream():
            words = text.split(" ")
            for idx, word in enumerate(words):
                is_last = idx == len(words) - 1
                chunk = {
                    "model": model,
                    "created_at": now_iso,
                    "response": word + (" " if not is_last else ""),
                    "done": is_last,
                }
                yield json.dumps(chunk) + "\n"
                await asyncio.sleep(0.015)

        return StreamingResponse(ollama_stream(), media_type="application/x-ndjson")

    return {
        "model": model,
        "created_at": now_iso,
        "response": text,
        "done": True,
        "total_duration": 120000000,
        "load_duration": 10000000,
        "prompt_eval_count": len(prompt.split()),
        "eval_count": len(text.split()),
    }


@router.post("/api/chat")
async def ollama_chat(payload: dict[str, Any]):
    messages = payload.get("messages", [])
    model = payload.get("model", "qwen2.5-coder:7b")
    stream = bool(payload.get("stream", False))

    last_prompt = messages[-1].get("content", "") if messages else ""
    try:
        gen_res = await inference_engine.generate(prompt=last_prompt, model=model)
        text = str(gen_res.get("text", f"Ollama chat output for {last_prompt}"))
    except Exception:
        text = f"Ollama chat output for {last_prompt}"

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if stream:

        async def ollama_chat_stream():
            words = text.split(" ")
            for idx, word in enumerate(words):
                is_last = idx == len(words) - 1
                chunk = {
                    "model": model,
                    "created_at": now_iso,
                    "message": {
                        "role": "assistant",
                        "content": word + (" " if not is_last else ""),
                    },
                    "done": is_last,
                }
                yield json.dumps(chunk) + "\n"
                await asyncio.sleep(0.015)

        return StreamingResponse(ollama_chat_stream(), media_type="application/x-ndjson")

    return {
        "model": model,
        "created_at": now_iso,
        "message": {"role": "assistant", "content": text},
        "done": True,
        "total_duration": 130000000,
        "eval_count": len(text.split()),
    }
