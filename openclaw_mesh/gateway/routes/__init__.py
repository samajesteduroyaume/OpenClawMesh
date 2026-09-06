"""Agrégateur et enregistreur des routeurs d'API de la passerelle OpenClawMesh."""

from __future__ import annotations

from fastapi import FastAPI

from .admin import router as admin_router
from .anthropic import router as anthropic_router
from .hub import router as hub_router
from .keys import router as keys_router
from .mcp import router as mcp_router
from .mesh import router as mesh_router
from .ollama import router as ollama_router
from .openai import router as openai_router
from .portal import router as portal_router
from .skills import router as skills_router


def register_routes(app: FastAPI) -> None:
    """Enregistre tous les sous-routeurs sur l'application FastAPI principale."""
    app.include_router(portal_router)
    app.include_router(keys_router)
    app.include_router(mesh_router)
    app.include_router(skills_router)
    app.include_router(openai_router)
    app.include_router(anthropic_router)
    app.include_router(ollama_router)
    app.include_router(mcp_router)
    app.include_router(admin_router)
    app.include_router(hub_router)


__all__ = [
    "register_routes",
    "portal_router",
    "keys_router",
    "mesh_router",
    "skills_router",
    "openai_router",
    "anthropic_router",
    "ollama_router",
    "mcp_router",
    "admin_router",
    "hub_router",
]
