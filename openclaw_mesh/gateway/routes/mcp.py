"""Routes Model Context Protocol (MCP) SSE et Messages JSON-RPC."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from ..state import mcp_service

logger = logging.getLogger("openclaw_mesh.gateway.routes.mcp")

router = APIRouter(tags=["MCP"])


@router.get("/mcp/sse")
async def mcp_sse_endpoint():
    """Établit un flux SSE pour un client Model Context Protocol (MCP)."""
    session_id = secrets.token_hex(16)
    return StreamingResponse(
        mcp_service.handle_sse_event_stream(session_id),
        media_type="text/event-stream",
    )


@router.post("/mcp/messages")
async def mcp_messages_endpoint(payload: dict[str, Any]):
    """Reçoit et traite les messages JSON-RPC 2.0 pour les sessions MCP SSE."""
    result = await mcp_service.handle_request(payload)
    return JSONResponse(result)
