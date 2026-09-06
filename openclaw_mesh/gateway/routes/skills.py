"""Routes d'exécution des compétences (Skills & Tasks)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from ..state import (
    ExecutePayload,
    _extract_api_key,
    _request_counter,
    _request_latencies,
    db,
    gateway_registry,
)

router = APIRouter(tags=["Skills & Execution"])


@router.post("/api/v1/execute")
async def execute_skill(
    payload_in: ExecutePayload,
    request: Request,
    x_api_key: str | None = Header(None),
):
    """
    Exécute une compétence pour un client authentifié.
    Vérifie la clé et traite la requête.
    """
    import openclaw_mesh.gateway.state as st

    key_str = _extract_api_key(request, x_api_key)
    key_rec = db.get_key(key_str)
    if not key_rec:
        raise HTTPException(status_code=403, detail="Clé d'API invalide.")

    valid, reason = key_rec.is_valid()
    if not valid:
        raise HTTPException(status_code=403, detail=f"Accès refusé : {reason}")

    t0 = time.perf_counter()
    skill_name = payload_in.skill
    payload = payload_in.payload
    handler = gateway_registry.get(skill_name)
    result = None

    if not db.reserve_usage(key_str, skill_name=skill_name):
        raise HTTPException(status_code=429, detail="Quota de requêtes épuisé.")

    try:
        if handler:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(payload)
            else:
                result = await asyncio.to_thread(handler, payload)
        elif (
            st.guichet_client
            and st.guichet_client.discovered_guichet_url
            and skill_name in ("llm", "chat", "code", "inference")
        ):
            prompt = payload.get("prompt", "")
            dispatch_res = await st.guichet_client.dispatch_ai_task(skill_name, prompt, payload)
            if dispatch_res and dispatch_res.get("status") == "routed":
                target_node = dispatch_res.get("target_node", {})
                target_name = target_node.get("name", "Nœud Maillage")
                result = {
                    "text": (
                        f"🤖 [OpenClaw Free Gateway · {target_name}] Réponse du maillage distribué pour : '{prompt}'"
                    ),
                    "model": payload.get("model", "qwen2.5-coder-free"),
                    "tokens": max(1, len(prompt.split())),
                    "mesh_routed": True,
                    "target_node": target_name,
                }
            else:
                result = {
                    "text": f"🤖 [OpenClaw Free Gateway] Réponse traitée pour : '{prompt}'",
                    "model": payload.get("model", "qwen2.5-coder-free"),
                    "tokens": max(1, len(prompt.split())),
                }
        elif skill_name == "llm":
            prompt = payload.get("prompt", "")
            result = {
                "text": f"🤖 [OpenClaw Free Gateway] Réponse traitée pour : '{prompt}'",
                "model": payload.get("model", "qwen2.5-coder-free"),
                "tokens": max(1, len(prompt.split())),
            }
        elif skill_name == "memory_search":
            query = payload.get("query", "")
            result = {
                "results": [
                    {
                        "doc_id": "free_doc_1",
                        "score": 0.96,
                        "content": f"Information indexée pour : {query}",
                    }
                ]
            }
        elif skill_name == "echo":
            result = payload
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Compétence '{skill_name}' non trouvée sur la passerelle.",
            )

        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        _request_counter["execute_total"] += 1
        _request_latencies.append(duration_ms / 1000.0)
        return {
            "ok": True,
            "result": result,
            "skill": skill_name,
            "duration_ms": duration_ms,
            "plan": key_rec.plan,
            "quota_used": key_rec.quota_used + 1,
        }

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        _request_counter["execute_errors"] += 1
        raise HTTPException(status_code=500, detail="Erreur d'exécution.") from e


@router.post("/api/v1/skills/{skill_name}")
async def execute_skill_direct(
    skill_name: str,
    payload: dict[str, Any],
    request: Request,
    x_api_key: str | None = Header(None),
):
    """Permet l'exécution directe d'une compétence par URL /api/v1/skills/{skill_name}."""
    return await execute_skill(
        payload_in=ExecutePayload(skill=skill_name, payload=payload),
        request=request,
        x_api_key=x_api_key,
    )
