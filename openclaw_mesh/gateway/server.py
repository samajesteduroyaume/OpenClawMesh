"""
Serveur FastAPI de Passerelle d'Inférence et de Commande OpenClawMesh (100% Free & Open-Access).

Architecture modulaire v1.2.0 :
- État partagé et cycle de vie : `openclaw_mesh.gateway.state`
- Sous-routeurs modulaires : `openclaw_mesh.gateway.routes`
"""

from __future__ import annotations

import os

import sys
import types
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .routes import register_routes
from .state import (
    ADMIN_TOKEN,
    DEFAULT_DB_PATH,
    _demo_issued_emails,
    _enforce_rate_limit,
    _extract_api_key,
    _is_admin_token_valid,
    _require_admin,
    _request_counter,
    _request_latencies,
    _settings,
    db,
    gateway_registry,
    inference_engine,
    kv_cache,
    lifespan,
    mcp_service,
    moe_orchestrator,
    multimodal_engine,
    reputation_mgr,
    start_wan_node,
    stop_wan_node,
)


class _ServerModule(types.ModuleType):
    """Permet aux tests et consommateurs d'accéder/modifier dynamiquement l'état du runtime."""

    @property
    def _wan_node(self):
        from . import state
        return state._wan_node

    @_wan_node.setter
    def _wan_node(self, val):
        from . import state
        state._wan_node = val

    @property
    def guichet_client(self):
        from . import state
        return state.guichet_client

    @guichet_client.setter
    def guichet_client(self, val):
        from . import state
        state.guichet_client = val

    @property
    def mesh_client(self):
        from . import state
        return state.mesh_client

    @mesh_client.setter
    def mesh_client(self, val):
        from . import state
        state.mesh_client = val


sys.modules[__name__].__class__ = _ServerModule

# ---------------------------------------------------------------------- #
# Initialisation de l'Application FastAPI
# ---------------------------------------------------------------------- #
app = FastAPI(
    title="OpenClawMesh — Free Gateway & Command Center",
    description="Passerelle d'Inférence IA Libre & Gratuite pour Agents Autonomes P2P",
    version="1.2.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("GATEWAY_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware de Rate Limiting
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        await _enforce_rate_limit(request)
    return await call_next(request)


# Enregistrement de tous les sous-routeurs modulaires
register_routes(app)

__all__ = [
    "app",
    "db",
    "ADMIN_TOKEN",
    "DEFAULT_DB_PATH",
    "inference_engine",
    "multimodal_engine",
    "moe_orchestrator",
    "kv_cache",
    "reputation_mgr",
    "mcp_service",
    "gateway_registry",
    "_wan_node",
    "guichet_client",
    "mesh_client",
    "lifespan",
    "start_wan_node",
    "stop_wan_node",
    "_is_admin_token_valid",
    "_require_admin",
    "_extract_api_key",
    "_request_counter",
    "_request_latencies",
    "_demo_issued_emails",
]
