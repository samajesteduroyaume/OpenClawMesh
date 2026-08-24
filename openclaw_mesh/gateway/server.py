"""
Serveur FastAPI de Passerelle de Monétisation (OpenClawMesh Gateway).

Gère :
- La réception des Webhooks Stripe & Lemon Squeezy (Cartes CB / Apple Pay / Payouts Revolut).
- L'émission automatique et la validation des clés d'API (sk_claw_...).
- L'authentification par clé et la déduction de quotas.
- L'exécution des compétences premium pour les agents OpenClaw.
- Le portail web client et le dashboard d'administration.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .db import KeyDatabase, KeyRecord
from .portal import render_portal_html
from ..bridge import SkillRegistry
from ..client import MeshClient

logger = logging.getLogger("openclaw_mesh.gateway")

# Configuration de l'environnement
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
LEMON_WEBHOOK_SECRET = os.getenv("LEMON_WEBHOOK_SECRET", "")
ADMIN_TOKEN = os.getenv("GATEWAY_ADMIN_TOKEN", "claw_admin_secret_2026")
DEFAULT_DB_PATH = os.getenv("GATEWAY_DB_PATH", "openclaw_keys.db")

app = FastAPI(
    title="OpenClawMesh — Monetization Gateway",
    description="Passerelle de Monétisation d'Agents IA & Validation de Clés d'API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instance de la base de données
db = KeyDatabase(DEFAULT_DB_PATH)

# Registre local des compétences exécutables par la passerelle
gateway_registry = SkillRegistry(name="gateway-engine")


# ---------------------------------------------------------------------- #
# Modèles de Données Pydantic
# ---------------------------------------------------------------------- #
class ExecutePayload(BaseModel):
    skill: str = Field(..., description="Nom de la compétence à exécuter")
    payload: dict[str, Any] = Field(default_factory=dict, description="Paramètres d'entrée")


class SimulateCheckoutPayload(BaseModel):
    email: str
    plan: str = "pro_monthly"
    amount: int = 1000


class CreateKeyAdminPayload(BaseModel):
    email: str
    plan: str = "custom"
    days_valid: Optional[int] = 30
    quota_limit: int = -1
    custom_prefix: str = "sk_claw_"


# ---------------------------------------------------------------------- #
# 1. Portail Web & Documentation
# ---------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
@app.get("/portal", response_class=HTMLResponse)
async def get_portal():
    """Affiche le portail web client d'achat et playground interactif."""
    return render_portal_html()


# ---------------------------------------------------------------------- #
# 2. Webhooks de Paiement (Stripe & Lemon Squeezy)
# ---------------------------------------------------------------------- #
@app.post("/api/webhooks/stripe")
async def handle_stripe_webhook(request: Request):
    """
    Traite les événements Stripe (Paiements CB, Apple Pay, abonnements).
    Génère automatiquement la clé d'API dès que checkout.session.completed est reçu.
    """
    raw_body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    event = None
    # Vérification cryptographique de signature Stripe si le secret est configuré
    if STRIPE_WEBHOOK_SECRET:
        try:
            import stripe
            event = stripe.Webhook.construct_event(
                payload=raw_body, sig_header=sig_header, secret=STRIPE_WEBHOOK_SECRET
            )
        except Exception as e:
            logger.error(f"Signature Stripe invalide: {e}")
            raise HTTPException(status_code=400, detail="Signature invalide")
    else:
        try:
            event = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"JSON invalide: {e}")

    event_type = event.get("type", "")
    event_id = event.get("id", f"evt_{secrets_id()}")
    data_obj = event.get("data", {}).get("object", {})

    logger.info(f"Webhook Stripe reçu : {event_type} (ID: {event_id})")

    # 1. Session de paiement réussie
    if event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        customer_email = data_obj.get("customer_details", {}).get("email") or data_obj.get("receipt_email") or "client@revolut.com"
        customer_id = data_obj.get("customer")
        subscription_id = data_obj.get("subscription")
        amount = data_obj.get("amount_total") or data_obj.get("amount", 1000)
        currency = data_obj.get("currency", "eur")

        # Détection du Plan (Pro Mensuel 10€ ou Licence à Vie 200€)
        if amount >= 15000 or "lifetime" in str(data_obj).lower():
            plan = "lifetime"
            days_valid = None  # Validité illimitée à vie
        else:
            plan = "pro_monthly"
            days_valid = 30  # 30 jours renouvelables

        # Enregistrer l'événement et créer la clé
        logged = db.log_payment_event(
            event_id=event_id,
            provider="stripe",
            event_type=event_type,
            customer_email=customer_email,
            amount_cents=amount,
            currency=currency,
            raw_payload=event,
        )

        if logged:
            key_record = db.create_key(
                email=customer_email,
                plan=plan,
                days_valid=days_valid,
                customer_id=customer_id,
                subscription_id=subscription_id,
                metadata={"provider": "stripe", "amount_paid": amount / 100.0},
            )
            logger.info(f"🎉 Clé créée pour {customer_email} : {key_record.key}")
            return {"status": "success", "action": "key_created", "api_key": key_record.key}

    # 2. Renouvellement automatique d'abonnement
    elif event_type == "invoice.payment_succeeded":
        sub_id = data_obj.get("subscription")
        if sub_id:
            db.renew_subscription(sub_id, days_extension=30)
            logger.info(f"🔄 Abonnement {sub_id} prolongé de 30 jours.")
            return {"status": "success", "action": "subscription_renewed"}

    # 3. Résiliation d'abonnement
    elif event_type == "customer.subscription.deleted":
        sub_id = data_obj.get("id")
        # Désactiver les clés liées
        with db._get_connection() as conn:
            conn.execute("UPDATE api_keys SET active = 0 WHERE subscription_id = ?", (sub_id,))
        return {"status": "success", "action": "subscription_canceled"}

    return {"status": "ignored", "event_type": event_type}


@app.post("/api/webhooks/lemonsqueezy")
async def handle_lemonsqueezy_webhook(request: Request):
    """Gère les notifications de vente Lemon Squeezy."""
    raw_body = await request.body()
    try:
        data = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail="JSON invalide")

    event_name = data.get("meta", {}).get("event_name", "")
    customer_email = data.get("data", {}).get("attributes", {}).get("user_email", "client@lemon.com")

    if event_name in ("order_created", "subscription_created"):
        key_record = db.create_key(
            email=customer_email,
            plan="pro_monthly",
            days_valid=30,
            metadata={"provider": "lemonsqueezy"},
        )
        return {"status": "success", "api_key": key_record.key}

    return {"status": "ignored"}


# ---------------------------------------------------------------------- #
# 3. Authentification & Exécution Sécurisée
# ---------------------------------------------------------------------- #
def _extract_api_key(request: Request, x_api_key: Optional[str] = Header(None)) -> str:
    """Extrait la clé d'API depuis le Header X-API-Key ou Authorization Bearer."""
    if x_api_key:
        return x_api_key.strip()

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    # Paramètre query en secours
    key_param = request.query_params.get("api_key")
    if key_param:
        return key_param.strip()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Clé d'API requise dans le header 'X-API-Key' ou 'Authorization: Bearer <clé>'",
    )


@app.post("/api/v1/auth/verify")
async def verify_key_endpoint(request: Request, x_api_key: Optional[str] = Header(None)):
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
        "expires_in_days": round((key_rec.expires_at - time.time()) / 86400, 1) if key_rec.expires_at else None,
    }


@app.post("/api/v1/execute")
async def execute_premium_skill(
    payload_in: ExecutePayload,
    request: Request,
    x_api_key: Optional[str] = Header(None),
):
    """
    Exécute une compétence protégée pour un client authentifié.
    Vérifie la clé, déduit le quota et traite la requête.
    """
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

    # 1. Vérifier si la compétence est enregistrée localement
    handler = gateway_registry.get(skill_name)
    result = None

    try:
        if handler:
            result = handler(payload)
        elif skill_name == "llm":
            # Inférence par défaut ou simulation
            prompt = payload.get("prompt", "")
            result = {
                "text": f"🤖 [OpenClaw Premium Gateway] Réponse traitée pour : '{prompt}'",
                "model": payload.get("model", "qwen2.5-coder-premium"),
                "tokens": 42,
            }
        elif skill_name == "memory_search":
            query = payload.get("query", "")
            result = {
                "results": [
                    {"doc_id": "premium_doc_1", "score": 0.96, "content": f"Information indexée pour : {query}"}
                ]
            }
        elif skill_name == "echo":
            result = payload
        else:
            raise HTTPException(status_code=404, detail=f"Compétence '{skill_name}' non trouvée sur la passerelle.")

        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        # Déduire le quota et enregistrer l'utilisation
        db.increment_usage(key_str, skill_name=skill_name, duration_ms=duration_ms, status="ok")

        return {
            "ok": True,
            "result": result,
            "skill": skill_name,
            "duration_ms": duration_ms,
            "plan": key_rec.plan,
            "quota_used": key_rec.quota_used + 1,
        }

    except Exception as e:
        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        db.increment_usage(key_str, skill_name=skill_name, duration_ms=duration_ms, status="error")
        raise HTTPException(status_code=500, detail=f"Erreur d'exécution: {e}")


# ---------------------------------------------------------------------- #
# 4. Helpers de Test & Administration
# ---------------------------------------------------------------------- #
@app.post("/api/v1/checkout/demo-key")
async def create_demo_key(payload: dict):
    """Crée instantanément une clé de démonstration (limitée à 3 requêtes)."""
    email = payload.get("email", "demo@openclaw.mesh")
    key_rec = db.create_key(
        email=email,
        plan="demo_free",
        days_valid=7,
        quota_limit=3,
        metadata={"is_demo": True},
    )
    return {"ok": True, "api_key": key_rec.key, "quota_limit": 3}


@app.post("/api/v1/checkout/simulate")
async def simulate_checkout(payload: SimulateCheckoutPayload):
    """Simule un paiement CB réussi (pratique pour tester l'onboarding)."""
    plan = payload.plan
    days = None if plan == "lifetime" else 30
    key_rec = db.create_key(
        email=payload.email,
        plan=plan,
        days_valid=days,
        metadata={"simulated_payment": True, "amount": payload.amount / 100.0},
    )
    return {"ok": True, "api_key": key_rec.key, "plan": plan}


@app.get("/api/v1/admin/keys")
async def admin_list_keys(token: str = Header(None, alias="X-Admin-Token")):
    """Liste toutes les clés enregistrées (protégé par mot de passe admin)."""
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Token admin invalide.")
    keys = db.list_all_keys()
    return {"count": len(keys), "keys": [k.to_dict() for k in keys]}


@app.post("/api/v1/admin/keys/create")
async def admin_create_key(payload: CreateKeyAdminPayload, token: str = Header(None, alias="X-Admin-Token")):
    """Création manuelle d'une clé par l'administrateur."""
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Token admin invalide.")
    key_rec = db.create_key(
        email=payload.email,
        plan=payload.plan,
        days_valid=payload.days_valid,
        quota_limit=payload.quota_limit,
        custom_prefix=payload.custom_prefix,
    )
    return {"ok": True, "key": key_rec.to_dict()}


def secrets_id() -> str:
    import secrets
    return secrets.token_hex(8)
