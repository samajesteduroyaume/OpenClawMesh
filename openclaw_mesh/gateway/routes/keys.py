"""Routes de génération et vérification de clés d'API (Free & Sovereign)."""

from __future__ import annotations

import re
import secrets
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from ..state import FreeKeyRequest, _demo_issued_emails, _extract_api_key, db

router = APIRouter(tags=["Keys"])


@router.post("/api/v1/checkout/free-key")
@router.post("/api/v1/keys/generate-free")
@router.post("/api/v1/auth/free-key")
async def generate_free_key(payload: FreeKeyRequest | None = None):
    """
    Génère instantanément et gratuitement une clé d'API OpenClawMesh sans aucun paiement ni carte.
    Accès communautaire complet et illimité.
    """
    email_in = (payload.email if payload else "").strip().lower()
    if not email_in:
        email_in = f"free_user_{secrets.token_hex(4)}@openclaw.mesh"
    elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_in):
        raise HTTPException(status_code=400, detail="Adresse email invalide.")

    key_rec = db.create_key(
        email=email_in,
        plan="free_community",
        days_valid=None,  # Pas d'expiration (accès libre permanent)
        quota_limit=-1,  # Requêtes illimitées
        metadata={"free_access": True, "created_via": "portal_instant"},
    )
    return {
        "ok": True,
        "api_key": key_rec.key,
        "key": key_rec.key,
        "plan": "free_community",
        "email": email_in,
        "quota_limit": -1,
        "expires_at": None,
        "message": "🎉 Clé d'API gratuite générée avec succès ! Accès libre et illimité.",
    }


@router.post("/api/v1/checkout/demo-key")
async def create_demo_key(payload: dict[str, Any]):
    """Crée instantanément une clé gratuite de démonstration."""
    email = payload.get("email", f"demo_{secrets.token_hex(4)}@openclaw.mesh")
    if (
        not isinstance(email, str)
        or len(email) > 320
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    ):
        raise HTTPException(status_code=400, detail="Adresse email invalide.")
    email = email.strip().lower()
    if email in _demo_issued_emails:
        raise HTTPException(status_code=429, detail="Une clé démo a déjà été créée pour cet email.")
    _demo_issued_emails.add(email)
    key_rec = db.create_key(
        email=email,
        plan="demo_free",
        days_valid=30,
        quota_limit=-1,
        metadata={"is_demo": True, "free": True},
    )
    return {"ok": True, "api_key": key_rec.key, "quota_limit": -1, "expires_in_days": 30}


@router.post("/api/v1/auth/verify")
async def verify_key_endpoint(request: Request, x_api_key: str | None = Header(None)):
    """Vérifie la validité d'une clé et retourne son statut."""
    key_str = _extract_api_key(request, x_api_key)
    key_rec = db.get_key(key_str)
    if not key_rec:
        return JSONResponse(status_code=404, content={"valid": False, "error": "Clé introuvable"})

    valid, reason = key_rec.is_valid()
    return {
        "valid": valid,
        "reason": reason,
        "email": key_rec.email,
        "plan": key_rec.plan,
        "quota_used": key_rec.quota_used,
        "quota_limit": key_rec.quota_limit,
        "expires_at": key_rec.expires_at,
        "expires_in_days": (
            round((key_rec.expires_at - time.time()) / 86400, 1) if key_rec.expires_at else None
        ),
    }
