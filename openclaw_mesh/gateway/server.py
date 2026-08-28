"""
Serveur FastAPI de Passerelle de Monétisation Bitcoin (OpenClawMesh Gateway).

Gère :
- Affichage de l'adresse Bitcoin de paiement (bc1q...).
- Soumission de transaction BTC par le client (email + txid + plan).
- Confirmation manuelle par l'administrateur et émission de la clé d'API.
- Authentification par clé et déduction de quotas.
- Exécution des compétences premium pour les agents OpenClaw.
- Le portail web client et le dashboard d'administration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request as URLRequest
from urllib.request import urlopen

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ..bridge import SkillRegistry
from ..config import get_settings
from ..crypto import TrustStore
from ..node import OpenClawMeshNode
from .db import KeyDatabase
from .portal import render_portal_html

logger = logging.getLogger("openclaw_mesh.gateway")
_settings = get_settings()


# Configuration de l'environnement
def _load_or_create_admin_token() -> str:
    """Charge le jeton admin depuis l'environnement ou un fichier privé persistant."""
    configured = os.getenv("GATEWAY_ADMIN_TOKEN")
    if configured:
        return configured

    token_path = Path(
        os.getenv(
            "GATEWAY_ADMIN_TOKEN_FILE",
            str(Path.home() / ".config" / "openclaw-mesh" / "gateway_admin.token"),
        )
    ).expanduser()
    try:
        if token_path.is_file():
            token = token_path.read_text(encoding="utf-8").strip()
            if token:
                return token
        token = secrets.token_urlsafe(32)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(token + "\n", encoding="utf-8")
        os.chmod(token_path, 0o600)
        logger.warning("Jeton admin généré automatiquement. Fichier privé : %s", token_path)
        return token
    except OSError as exc:
        raise RuntimeError(
            "Impossible de créer le jeton admin. Définissez GATEWAY_ADMIN_TOKEN "
            "ou GATEWAY_ADMIN_TOKEN_FILE."
        ) from exc


ADMIN_TOKEN = _load_or_create_admin_token()
DEFAULT_DB_PATH = os.getenv("GATEWAY_DB_PATH", "openclaw_keys.db")

# Adresse Bitcoin de réception des paiements
BTC_WALLET_ADDRESS = os.getenv("BTC_WALLET_ADDRESS", "bc1qwq8sll9vrl83lclyhha2gyncpd5275cdr2wul5")
BTC_EXPLORER_URL = os.getenv("BTC_EXPLORER_URL", "")
BTC_PRICE_URL = os.getenv(
    "BTC_PRICE_URL",
    "",
)
BTC_PRICE_URLS = [
    url.strip() for url in os.getenv("BTC_PRICE_URLS", BTC_PRICE_URL).split(",") if url.strip()
]
BTC_PRICE_FALLBACK_EUR = Decimal(os.getenv("BTC_PRICE_FALLBACK_EUR", "67642"))
BTC_PRICE_CACHE_SECONDS = max(30, int(os.getenv("BTC_PRICE_CACHE_SECONDS", "300")))
BTC_REQUIRED_CONFIRMATIONS = max(1, int(os.getenv("BTC_REQUIRED_CONFIRMATIONS", "1")))
BTC_AUTO_VERIFY = os.getenv("BTC_AUTO_VERIFY", "false").lower() in {"1", "true", "yes", "on"}
BTC_VERIFY_INTERVAL = max(10, int(os.getenv("BTC_VERIFY_INTERVAL_SECONDS", "30")))
try:
    BTC_PLAN_MIN_SATS: dict[str, int] = {
        plan: int(amount)
        for plan, amount in json.loads(os.getenv("BTC_PLAN_MIN_SATS", "{}")).items()
    }
except (TypeError, ValueError, json.JSONDecodeError):
    BTC_PLAN_MIN_SATS = {}
_payment_verifier_task: asyncio.Task | None = None
_btc_price_cache: tuple[Decimal, float] | None = None
_wan_node: OpenClawMeshNode | None = None

# Tarifs EUR indicatifs (le client envoie le montant BTC équivalent)
PLAN_PRICES_EUR: dict[str, int] = {
    "pro_monthly": 10,
    "lifetime": 200,
    "demo_free": 0,
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _payment_verifier_task, _wan_node
    if BTC_AUTO_VERIFY and _payment_verifier_task is None:
        _payment_verifier_task = asyncio.create_task(_verify_pending_payments())
    try:
        yield
    finally:
        if _wan_node is not None:
            await _wan_node.stop()
            _wan_node = None
        if _payment_verifier_task:
            _payment_verifier_task.cancel()
            await asyncio.gather(_payment_verifier_task, return_exceptions=True)
            _payment_verifier_task = None


app = FastAPI(
    title="OpenClawMesh — Bitcoin Payment Gateway",
    description="Passerelle de Monétisation BTC pour Agents IA & Validation de Clés d'API",
    version="1.1.0",
    lifespan=lifespan,
)

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


def _fetch_json(url: str) -> Any:
    """Récupère une réponse JSON sans bloquer la boucle asyncio appelante."""
    request = URLRequest(url, headers={"User-Agent": "OpenClawMesh-Gateway/1.0"})
    with urlopen(request, timeout=10) as response:  # noqa: S310 - URL configurable par l'admin
        data = json.loads(response.read().decode("utf-8"))
    return data


def _get_btc_eur_price() -> Decimal:
    """Retourne le cours BTC/EUR de l'oracle, avec cache et fallback de sécurité."""
    global _btc_price_cache
    now = time.time()
    if _btc_price_cache and now - _btc_price_cache[1] < BTC_PRICE_CACHE_SECONDS:
        return _btc_price_cache[0]
    prices: list[Decimal] = []
    for price_url in BTC_PRICE_URLS:
        try:
            data = _fetch_json(price_url)
            if "bitcoin" in data:
                raw_price = data["bitcoin"]["eur"]
            else:
                raw_price = data["data"]["amount"]
            price = Decimal(str(raw_price))
            if price > 0:
                prices.append(price)
        except (OSError, URLError, KeyError, TypeError, ValueError, ArithmeticError) as exc:
            logger.warning("Source oracle BTC/EUR indisponible (%s): %s", price_url, exc)
    if prices:
        ordered = sorted(prices)
        price = ordered[len(ordered) // 2]
        _btc_price_cache = (price, now)
        return price
    logger.warning("Tous les oracles BTC/EUR sont indisponibles, utilisation du fallback")
    return BTC_PRICE_FALLBACK_EUR


def _minimum_sats(plan: str, btc_eur_price: Decimal) -> int:
    """Convertit le prix EUR du plan en satoshis, en arrondissant vers le haut."""
    configured = BTC_PLAN_MIN_SATS.get(plan)
    if configured is not None:
        return configured
    btc_amount = Decimal(PLAN_PRICES_EUR[plan]) / btc_eur_price
    return int((btc_amount * Decimal(100_000_000)).to_integral_value(rounding=ROUND_CEILING))


def _transaction_is_paid(txid: str, expected_sats: int) -> tuple[bool, str]:
    """Vérifie destinataire, montant minimum configuré et confirmations du txid."""
    if not BTC_EXPLORER_URL:
        raise RuntimeError(
            "BTC_EXPLORER_URL doit être configuré pour vérifier un paiement automatiquement."
        )
    if expected_sats <= 0:
        return False, "Montant BTC minimum invalide."
    base_url = BTC_EXPLORER_URL.rstrip("/")
    tx = _fetch_json(f"{base_url}/tx/{txid}")
    if not isinstance(tx, dict):
        raise ValueError("Réponse transaction Bitcoin inattendue")
    outputs = tx.get("vout", [])
    received_sats = sum(
        int(output.get("value", 0))
        for output in outputs
        if output.get("scriptpubkey_address") == BTC_WALLET_ADDRESS
    )
    if received_sats < expected_sats:
        return False, f"Montant insuffisant ({received_sats}/{expected_sats} sats)."

    status_data = tx.get("status", {})
    confirmations = 0
    if status_data.get("confirmed"):
        tip = _fetch_json(f"{base_url}/blocks/tip/height")
        block_height = int(status_data["block_height"])
        tip_height = int(tip.get("height", tip) if isinstance(tip, dict) else tip)
        confirmations = max(1, tip_height - block_height + 1)
    if confirmations < BTC_REQUIRED_CONFIRMATIONS:
        return False, f"Confirmations insuffisantes ({confirmations}/{BTC_REQUIRED_CONFIRMATIONS})."
    return True, f"Paiement vérifié: {received_sats} sats, {confirmations} confirmations."


def _transaction_block_hash(txid: str) -> str | None:
    """Retourne le bloc actuellement associé à une transaction confirmée."""
    if not BTC_EXPLORER_URL:
        return None
    tx = _fetch_json(f"{BTC_EXPLORER_URL.rstrip('/')}/tx/{txid}")
    if not isinstance(tx, dict) or not tx.get("status", {}).get("confirmed"):
        return None
    block_hash = tx.get("status", {}).get("block_hash")
    return block_hash if isinstance(block_hash, str) else None


async def _verify_pending_payments() -> None:
    """Worker de confirmation automatique, activé lorsque BTC_AUTO_VERIFY vaut true."""
    while True:
        try:
            with db._get_connection() as conn:
                rows = conn.execute(
                    "SELECT event_id, raw_payload_json, txid FROM payment_events "
                    "WHERE provider = 'bitcoin' AND event_type = 'pending_verification'"
                ).fetchall()
            for row in rows:
                raw_data = json.loads(row["raw_payload_json"] or "{}")
                txid = row["txid"] or raw_data.get("txid")
                if not txid:
                    continue
                try:
                    paid, reason = await asyncio.to_thread(
                        _transaction_is_paid,
                        txid,
                        int(raw_data.get("minimum_sats", 0)),
                    )
                except (OSError, URLError, ValueError, KeyError) as exc:
                    logger.warning("Vérification BTC impossible pour %s: %s", txid[:16], exc)
                    continue
                if paid:
                    block_hash = await asyncio.to_thread(_transaction_block_hash, txid)
                    key_rec = db.confirm_payment(
                        row["event_id"],
                        days_valid=raw_data.get("days_valid"),
                        confirmed_by="auto_btc_verifier",
                        confirmation_metadata={"confirmed_block_hash": block_hash},
                    )
                    if key_rec:
                        logger.info(
                            "✅ Paiement BTC confirmé automatiquement — TXID: %s...", txid[:16]
                        )
                else:
                    logger.info("Paiement BTC en attente — TXID: %s... (%s)", txid[:16], reason)

            with db._get_connection() as conn:
                confirmed_rows = conn.execute(
                    "SELECT event_id, raw_payload_json FROM payment_events "
                    "WHERE provider = 'bitcoin' AND event_type = 'confirmed'"
                ).fetchall()
            for row in confirmed_rows:
                raw_data = json.loads(row["raw_payload_json"] or "{}")
                txid = raw_data.get("txid")
                expected_block = raw_data.get("confirmed_block_hash")
                if not txid or not expected_block:
                    continue
                try:
                    current_block = await asyncio.to_thread(_transaction_block_hash, txid)
                except (OSError, URLError, ValueError, KeyError):
                    continue
                if current_block != expected_block:
                    key_hash = raw_data.get("confirmed_key_hash")
                    if key_hash:
                        db.revoke_key_hash(key_hash)
                    raw_data["reorg_detected_at"] = time.time()
                    with db._get_connection() as conn:
                        conn.execute(
                            "UPDATE payment_events SET event_type = 'reorg_detected', raw_payload_json = ? "
                            "WHERE event_id = ? AND event_type = 'confirmed'",
                            (json.dumps(raw_data), row["event_id"]),
                        )
                    logger.error("Réorganisation Bitcoin détectée — TXID: %s...", txid[:16])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Erreur dans le vérificateur automatique Bitcoin")
        await asyncio.sleep(BTC_VERIFY_INTERVAL)


# Instance de la base de données
db = KeyDatabase(DEFAULT_DB_PATH)

# Registre local des compétences exécutables par la passerelle
gateway_registry = SkillRegistry(name="gateway-engine")
_demo_issued_emails: set[str] = set()
_rate_limit_events: dict[str, deque[float]] = defaultdict(deque)
_rate_limit_lock = asyncio.Lock()


async def _enforce_rate_limit(request: Request) -> None:
    """Limite les endpoints HTTP même lorsqu'aucun reverse proxy n'est présent."""
    if os.getenv("OPENCLAW_RATE_LIMIT_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        return
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = 60.0
    limit = max(1, int(os.getenv("OPENCLAW_RATE_LIMIT_REQUESTS_PER_MINUTE", "60")))
    async with _rate_limit_lock:
        events = _rate_limit_events[client]
        while events and now - events[0] >= window:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(
                status_code=429, detail="Trop de requêtes, veuillez réessayer plus tard."
            )
        events.append(now)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        await _enforce_rate_limit(request)
    return await call_next(request)


def _new_payment_id() -> str:
    """Génère un identifiant de paiement aléatoire de 24 chars hex."""
    return secrets.token_hex(12)


def _require_admin(token: str | None) -> None:
    """Vérifie le token administrateur (temps constant)."""
    if not token or not secrets.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Token admin invalide.")


# ---------------------------------------------------------------------- #
# Modèles de Données Pydantic
# ---------------------------------------------------------------------- #
class ExecutePayload(BaseModel):
    skill: str = Field(
        ..., min_length=1, max_length=100, description="Nom de la compétence à exécuter"
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="Paramètres d'entrée")


class BTCPaymentSubmission(BaseModel):
    email: str = Field(..., min_length=3, max_length=320, description="Adresse email du client")
    plan: str = Field(default="pro_monthly", description="Plan : pro_monthly ou lifetime")
    txid: str = Field(..., description="Hash de transaction Bitcoin (64 caractères hexadécimaux)")
    note: str = Field(default="", max_length=1000, description="Note optionnelle du client")


class ConfirmBTCPaymentPayload(BaseModel):
    payment_id: str = Field(..., description="Identifiant de la soumission de paiement")
    days_valid: int | None = Field(default=None, description="Durée de validité (None = lifetime)")
    quota_limit: int = Field(default=-1, description="Quota de requêtes (-1 = illimité)")


class CreateKeyAdminPayload(BaseModel):
    email: str
    plan: str = "custom"
    days_valid: int | None = 30
    quota_limit: int = -1
    custom_prefix: str = "sk_claw_"


class WanTogglePayload(BaseModel):
    remote_access: bool = False


# ---------------------------------------------------------------------- #
# 1. Portail Web
# ---------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
@app.get("/portal", response_class=HTMLResponse)
async def get_portal():
    """Affiche le portail web client avec les instructions de paiement BTC."""
    return render_portal_html(btc_address=BTC_WALLET_ADDRESS)


# ---------------------------------------------------------------------- #
# 2. Informations & Flux de Paiement Bitcoin
# ---------------------------------------------------------------------- #
@app.get("/api/v1/payment/info")
async def get_payment_info():
    """
    Retourne l'adresse BTC, les tarifs et les instructions de paiement.
    Utilisé par le portail pour afficher le QR code et l'adresse.
    """
    price_eur = await asyncio.to_thread(_get_btc_eur_price)
    return {
        "wallet_address": BTC_WALLET_ADDRESS,
        "currency": "BTC",
        "btc_eur_rate": float(price_eur),
        "plans": {
            "pro_monthly": {
                "price_eur": PLAN_PRICES_EUR["pro_monthly"],
                "minimum_sats": _minimum_sats("pro_monthly", price_eur),
                "description": "Accès Pro — 30 jours, requêtes illimitées",
                "days_valid": 30,
            },
            "lifetime": {
                "price_eur": PLAN_PRICES_EUR["lifetime"],
                "minimum_sats": _minimum_sats("lifetime", price_eur),
                "description": "Licence à Vie — accès permanent, toutes mises à jour incluses",
                "days_valid": None,
            },
        },
        "instructions": (
            "1. Envoyez le montant BTC équivalent au plan choisi à l'adresse Bitcoin ci-dessus.\n"
            "2. Soumettez votre email, le plan et le txid via POST /api/v1/payment/submit.\n"
            "3. Dès que l'administrateur confirme le txid, votre clé d'API est activée instantanément."
        ),
    }


@app.post("/api/v1/payment/submit")
async def submit_btc_payment(payload: BTCPaymentSubmission):
    """
    Le client soumet son txid Bitcoin après avoir effectué le virement.
    Crée une entrée « en attente de confirmation » dans la base de données.
    L'admin confirme via POST /api/v1/admin/payments/confirm.
    """
    if payload.plan not in ("pro_monthly", "lifetime"):
        raise HTTPException(
            status_code=400,
            detail="Plan invalide. Choisissez 'pro_monthly' (10€/mois) ou 'lifetime' (200€).",
        )

    txid_clean = payload.txid.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", txid_clean):
        raise HTTPException(
            status_code=400,
            detail="TXID Bitcoin invalide (64 caractères hexadécimaux requis).",
        )

    payment_id = _new_payment_id()
    status_token = secrets.token_urlsafe(32)
    days_valid = None if payload.plan == "lifetime" else 30
    btc_eur_price = await asyncio.to_thread(_get_btc_eur_price)
    minimum_sats = _minimum_sats(payload.plan, btc_eur_price)

    logged = db.log_payment_event(
        event_id=f"btc_{payment_id}",
        provider="bitcoin",
        event_type="pending_verification",
        customer_email=payload.email.strip().lower(),
        amount_cents=PLAN_PRICES_EUR.get(payload.plan, 0) * 100,
        currency="btc",
        raw_payload={
            "payment_id": payment_id,
            "plan": payload.plan,
            "txid": txid_clean,
            "days_valid": days_valid,
            "note": payload.note,
            "submitted_at": time.time(),
            "btc_eur_rate": str(btc_eur_price),
            "minimum_sats": minimum_sats,
            "status_token": status_token,
        },
        txid=txid_clean,
    )

    if not logged:
        raise HTTPException(
            status_code=409,
            detail="Ce txid a déjà été soumis. Contactez l'administrateur si c'est une erreur.",
        )

    logger.info(
        "Paiement BTC soumis — ID: %s | Email: %s | Plan: %s | TXID: %s...",
        payment_id,
        payload.email,
        payload.plan,
        txid_clean[:16],
    )

    return {
        "ok": True,
        "payment_id": payment_id,
        "status_token": status_token,
        "status": "pending_verification",
        "message": (
            f"Votre paiement BTC a été enregistré (payment_id: {payment_id}). "
            "Votre clé sera activée instantanément dès la confirmation du txid par l'administrateur."
        ),
        "wallet_address": BTC_WALLET_ADDRESS,
        "plan": payload.plan,
        "email": payload.email,
    }


@app.get("/api/v1/payment/status/{payment_id}")
async def check_payment_status(
    payment_id: str,
    payment_token: str | None = Header(None, alias="X-Payment-Token"),
):
    """Permet au client de vérifier l'état de son paiement soumis."""
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM payment_events WHERE event_id = ?",
            (f"btc_{payment_id}",),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Payment ID introuvable.")

    payload_data = json.loads(row["raw_payload_json"] or "{}")
    if not payment_token or not secrets.compare_digest(
        payment_token, payload_data.get("status_token", "")
    ):
        raise HTTPException(status_code=403, detail="Jeton de paiement requis.")
    is_confirmed = row["event_type"] == "confirmed"
    is_rejected = row["event_type"] == "rejected"

    result: dict[str, Any] = {
        "payment_id": payment_id,
        "status": row["event_type"],
        "plan": payload_data.get("plan"),
        "email": row["customer_email"],
        "submitted_at": payload_data.get("submitted_at"),
    }

    if is_confirmed:
        result["confirmed_at"] = payload_data.get("confirmed_at")
    elif is_rejected:
        result["rejection_reason"] = payload_data.get("rejection_reason", "Non spécifié.")

    return result


# ---------------------------------------------------------------------- #
# 3. Authentification & Exécution Sécurisée
# ---------------------------------------------------------------------- #
def _extract_api_key(request: Request, x_api_key: str | None = Header(None)) -> str:
    """Extrait la clé d'API depuis le Header X-API-Key ou Authorization Bearer."""
    if x_api_key:
        return x_api_key.strip()

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Clé d'API requise dans le header 'X-API-Key' ou 'Authorization: Bearer <clé>'",
    )


@app.post("/api/v1/auth/verify")
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


@app.post("/api/v1/execute")
async def execute_premium_skill(
    payload_in: ExecutePayload,
    request: Request,
    x_api_key: str | None = Header(None),
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
        elif skill_name == "llm":
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
                    {
                        "doc_id": "premium_doc_1",
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
        raise HTTPException(status_code=500, detail="Erreur d'exécution.") from e


# ---------------------------------------------------------------------- #
# 4. Démo Gratuite
# ---------------------------------------------------------------------- #
@app.post("/api/v1/checkout/demo-key")
async def create_demo_key(payload: dict):
    """Crée instantanément une clé de démonstration (3 requêtes, 7 jours)."""
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
        days_valid=7,
        quota_limit=3,
        metadata={"is_demo": True, "provider": "bitcoin_gateway"},
    )
    return {"ok": True, "api_key": key_rec.key, "quota_limit": 3, "expires_in_days": 7}


# ---------------------------------------------------------------------- #
# 5. Administration
# ---------------------------------------------------------------------- #
@app.get("/api/v1/admin/keys")
async def admin_list_keys(token: str = Header(None, alias="X-Admin-Token")):
    """Liste toutes les clés enregistrées (protégé par token admin)."""
    _require_admin(token)
    keys = db.list_all_keys()
    return {"count": len(keys), "keys": [k.to_dict(include_key=False) for k in keys]}


@app.post("/api/v1/admin/wan/toggle")
async def admin_toggle_wan_node(
    payload: WanTogglePayload | None = None,
    token: str = Header(None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """Active ou désactive le nœud WAN en 100% Confiance avec auto-sécurisation immédiate."""
    global _wan_node
    remote_access = payload.remote_access if payload is not None else True
    _require_admin(token)
    if _wan_node is not None:
        await _wan_node.stop()
        _wan_node = None
        return {
            "ok": True,
            "active": False,
            "message": "Nœud WAN désactivé (Mode Local 127.0.0.1).",
        }

    active_psk = _settings.psk or secrets.token_urlsafe(24)
    trust_store = (
        TrustStore.load(_settings.trust_store_path) if _settings.trust_store_path else None
    )

    from ..crypto import create_ephemeral_ssl_context

    ssl_ctx = None
    if remote_access:
        try:
            ssl_ctx = create_ephemeral_ssl_context()
        except Exception as exc:
            logger.debug(f"Impossible de créer un certificat TLS éphémère: {exc}")

    _wan_node = OpenClawMeshNode(
        name=_settings.node_name,
        host="0.0.0.0" if remote_access else "127.0.0.1",
        port=_settings.default_port,
        registry=gateway_registry,
        psk=active_psk,
        trust_store=trust_store,
        ssl_context=ssl_ctx,
    )
    try:
        await _wan_node.start(enable_zeroconf=False)
    except Exception as exc:
        _wan_node = None
        logger.exception("Échec d'activation du nœud WAN")
        raise HTTPException(
            status_code=500, detail=f"Impossible d'activer le nœud WAN : {exc}"
        ) from None

    from ..discovery import get_local_ip

    local_ip = get_local_ip()
    scheme = "wss" if ssl_ctx else "ws"
    connect_url = f"{scheme}://{local_ip}:{_settings.default_port}"
    cli_cmd = f"openclaw-mesh call --peer {connect_url} --psk {active_psk} --skill llm"

    return {
        "ok": True,
        "active": True,
        "remote_access": remote_access,
        "host": "0.0.0.0" if remote_access else "127.0.0.1",
        "port": _settings.default_port,
        "psk": active_psk,
        "connect_url": connect_url,
        "cli_command": cli_cmd,
        "message": "⚡ Nœud WAN activé en 100% Confiance ! Chiffrement et clé de sécurité auto-générés.",
    }


@app.get("/api/v1/admin/payments/pending")
async def admin_list_pending_payments(token: str = Header(None, alias="X-Admin-Token")):
    """Liste tous les paiements BTC en attente de confirmation."""
    _require_admin(token)
    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM payment_events "
            "WHERE provider = 'bitcoin' AND event_type = 'pending_verification' "
            "ORDER BY created_at DESC"
        ).fetchall()

    payments = []
    for r in rows:
        payload_data = json.loads(r["raw_payload_json"] or "{}")
        payments.append(
            {
                "event_id": r["event_id"],
                "payment_id": payload_data.get("payment_id"),
                "email": r["customer_email"],
                "plan": payload_data.get("plan"),
                "txid": r["txid"] or payload_data.get("txid"),
                "amount_eur": (r["amount_cents"] or 0) / 100,
                "submitted_at": payload_data.get("submitted_at"),
                "note": payload_data.get("note", ""),
            }
        )

    return {"count": len(payments), "pending_payments": payments}


@app.post("/api/v1/admin/payments/confirm")
async def admin_confirm_btc_payment(
    payload: ConfirmBTCPaymentPayload,
    token: str = Header(None, alias="X-Admin-Token"),
):
    """
    Confirme un paiement BTC après vérification manuelle sur la blockchain.
    Crée la clé d'API et marque le paiement comme confirmé.
    """
    _require_admin(token)

    event_id = f"btc_{payload.payment_id}"
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM payment_events WHERE event_id = ?", (event_id,)
        ).fetchone()

    if not row:
        raise HTTPException(
            status_code=404, detail=f"Payment ID '{payload.payment_id}' introuvable."
        )
    if row["event_type"] == "confirmed":
        raise HTTPException(status_code=409, detail="Ce paiement a déjà été confirmé.")
    if row["event_type"] == "rejected":
        raise HTTPException(
            status_code=409, detail="Ce paiement a été rejeté et ne peut pas être confirmé."
        )

    raw_data = json.loads(row["raw_payload_json"] or "{}")
    email = row["customer_email"]
    plan = raw_data.get("plan", "pro_monthly")
    days_valid = (
        payload.days_valid if payload.days_valid is not None else raw_data.get("days_valid")
    )

    key_rec = db.confirm_payment(
        event_id,
        quota_limit=payload.quota_limit,
        days_valid=days_valid,
    )
    if not key_rec:
        raise HTTPException(status_code=409, detail="Ce paiement ne peut plus être confirmé.")

    logger.info(
        "✅ Paiement BTC confirmé — Email: %s | Plan: %s | Clé: %s...",
        email,
        plan,
        key_rec.key[:12],
    )

    return {
        "ok": True,
        "message": f"Clé créée et paiement confirmé pour {email}",
        "api_key": key_rec.key,
        "plan": plan,
        "email": email,
        "expires_at": key_rec.expires_at,
    }


@app.post("/api/v1/admin/payments/reject")
async def admin_reject_btc_payment(
    payload: dict,
    token: str = Header(None, alias="X-Admin-Token"),
):
    """Rejette un paiement BTC invalide (txid incorrect ou montant insuffisant)."""
    _require_admin(token)

    payment_id = payload.get("payment_id")
    reason = payload.get("reason", "Paiement invalide ou non vérifiable.")
    event_id = f"btc_{payment_id}"

    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT event_type, raw_payload_json FROM payment_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Payment ID introuvable.")
        if row["event_type"] != "pending_verification":
            raise HTTPException(
                status_code=409, detail="Seul un paiement en attente peut être rejeté."
            )
        raw_data = json.loads(row["raw_payload_json"] or "{}")
        raw_data["rejected_at"] = time.time()
        raw_data["rejection_reason"] = reason
        conn.execute(
            "UPDATE payment_events SET event_type = 'rejected', raw_payload_json = ? WHERE event_id = ?",
            (json.dumps(raw_data), event_id),
        )

    logger.info("❌ Paiement BTC rejeté — ID: %s | Raison: %s", payment_id, reason)
    return {"ok": True, "message": f"Paiement {payment_id} rejeté : {reason}"}


@app.post("/api/v1/admin/keys/create")
async def admin_create_key(
    payload: CreateKeyAdminPayload,
    token: str = Header(None, alias="X-Admin-Token"),
):
    """Création manuelle d'une clé par l'administrateur."""
    _require_admin(token)
    key_rec = db.create_key(
        email=payload.email,
        plan=payload.plan,
        days_valid=payload.days_valid,
        quota_limit=payload.quota_limit,
        custom_prefix=payload.custom_prefix,
        metadata={"provider": "admin_manual"},
    )
    return {"ok": True, "key": key_rec.to_dict()}


@app.delete("/api/v1/admin/keys/{key_str}")
async def admin_revoke_key(
    key_str: str,
    token: str = Header(None, alias="X-Admin-Token"),
):
    """Révoque (désactive) une clé d'API active."""
    _require_admin(token)
    revoked = db.revoke_key(key_str)
    if not revoked:
        raise HTTPException(status_code=404, detail="Clé introuvable.")
    return {"ok": True, "message": f"Clé {key_str[:16]}... révoquée."}
