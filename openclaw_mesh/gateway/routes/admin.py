"""Routes d'administration de la passerelle (Gestion des clés et pilotage WAN)."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from ...config import get_settings
from ...crypto import TrustStore
from ...node import OpenClawMeshNode
from ..state import (
    CreateKeyAdminPayload,
    WanTogglePayload,
    _is_admin_token_valid,
    _require_admin,
    db,
    gateway_registry,
    start_wan_node,
    stop_wan_node,
)

logger = logging.getLogger("openclaw_mesh.gateway.routes.admin")
_settings = get_settings()

router = APIRouter(tags=["Admin"])


@router.post("/api/v1/admin/auth/verify")
async def admin_auth_verify(
    request: Request,
    token: str | None = Header(None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """Vérifie l'authenticité du jeton Administrateur Maître Guichet Freebox."""
    if not _is_admin_token_valid(token):
        raise HTTPException(status_code=401, detail="Token administrateur invalide.")
    return {
        "ok": True,
        "role": "master_admin",
        "guichet": "Freebox Ultra Master",
        "message": "Session Administrateur Maître Guichet Freebox validée avec succès.",
    }


@router.get("/api/v1/admin/keys")
async def admin_list_keys(
    request: Request,
    token: str = Header(None, alias="X-Admin-Token"),
):
    """Liste toutes les clés enregistrées (protégé par token admin)."""
    _require_admin(token, request)
    keys = db.list_all_keys()
    return {"count": len(keys), "keys": [k.to_dict(include_key=False) for k in keys]}


@router.post("/api/v1/admin/wan/toggle")
async def admin_toggle_wan_node(
    request: Request,
    payload: WanTogglePayload | None = None,
    token: str = Header(None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """Active ou désactive le nœud WAN en 100% Confiance avec auto-sécurisation immédiate."""
    import openclaw_mesh.gateway.state as st

    remote_access = payload.remote_access if payload is not None else True
    _require_admin(token, request)
    if st._wan_node is not None:
        await stop_wan_node()
        return {
            "ok": True,
            "active": False,
            "message": "Nœud WAN désactivé (Mode Local 127.0.0.1).",
        }

    try:
        node = await start_wan_node(remote_access=remote_access)
    except Exception as exc:
        logger.exception("Échec d'activation du nœud WAN")
        raise HTTPException(
            status_code=500, detail=f"Impossible d'activer le nœud WAN : {exc}"
        ) from None

    from ...discovery import get_local_ip

    local_ip = get_local_ip()
    scheme = "wss" if node.ssl_context else "ws"
    connect_url = f"{scheme}://{local_ip}:{_settings.default_port}"
    cli_cmd = f"openclaw-mesh call --peer {connect_url} --psk {node.psk} --skill llm"

    return {
        "ok": True,
        "active": True,
        "remote_access": remote_access,
        "host": "0.0.0.0" if remote_access else "127.0.0.1",
        "port": _settings.default_port,
        "psk": node.psk,
        "connect_url": connect_url,
        "cli_command": cli_cmd,
        "message": "⚡ Nœud WAN activé en 100% Confiance ! Chiffrement TLS et clé de sécurité auto-générés.",
    }


@router.post("/api/v1/admin/keys/create")
async def admin_create_key(
    request: Request,
    payload: CreateKeyAdminPayload,
    token: str = Header(None, alias="X-Admin-Token"),
):
    """Création manuelle d'une clé par l'administrateur."""
    _require_admin(token, request)
    key_rec = db.create_key(
        email=payload.email,
        plan=payload.plan,
        days_valid=payload.days_valid,
        quota_limit=payload.quota_limit,
        custom_prefix=payload.custom_prefix,
        metadata={"provider": "admin_manual"},
    )
    return {"ok": True, "key": key_rec.to_dict()}


@router.delete("/api/v1/admin/keys/{key_str}")
async def admin_revoke_key(
    request: Request,
    key_str: str,
    token: str = Header(None, alias="X-Admin-Token"),
):
    """Révoque (désactive) une clé d'API active."""
    _require_admin(token, request)
    revoked = db.revoke_key(key_str)
    if not revoked:
        raise HTTPException(status_code=404, detail="Clé introuvable.")
    return {"ok": True, "message": f"Clé {key_str[:16]}... révoquée."}
