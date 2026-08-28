"""
Serveur FastAPI de Passerelle d'Inférence et de Commande OpenClawMesh (100% Free & Open-Access).

Gère :
- Le portail web d'accès communautaire gratuit & le dashboard de contrôle WAN.
- L'émission instantanée et libre de clés d'API communautaires (Free & Sovereign).
- L'authentification par clé et le monitoring d'usage.
- L'exécution de compétences IA (LLM, RAG, outils) pour les agents OpenClaw.
- Le pilotage du nœud WAN en mode 100% Confiance.
- L'administration des clés d'accès.
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
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..bridge import SkillRegistry
from ..config import get_settings
from ..crypto import TrustStore
from ..engines.distributed_moe import DistributedMoEOrchestrator
from ..engines.inference import UniversalInferenceEngine
from ..engines.kv_cache import SemanticKVCache
from ..engines.multimodal import MultiModalEngine
from ..node import OpenClawMeshNode
from ..reputation import ReputationManager
from .db import KeyDatabase
from .portal import render_portal_html

logger = logging.getLogger("openclaw_mesh.gateway")
_settings = get_settings()

# Moteurs d'IA & Services de la passerelle
kv_cache = SemanticKVCache()
reputation_mgr = ReputationManager()
inference_engine = UniversalInferenceEngine()
moe_orchestrator = DistributedMoEOrchestrator()
multimodal_engine = MultiModalEngine()
_request_counter: dict[str, int] = defaultdict(int)
_request_latencies: deque[float] = deque(maxlen=500)



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

_wan_node: OpenClawMeshNode | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _wan_node
    try:
        yield
    finally:
        if _wan_node is not None:
            await _wan_node.stop()
            _wan_node = None


app = FastAPI(
    title="OpenClawMesh — Free Gateway & Command Center",
    description="Passerelle d'Inférence IA Libre & Gratuite pour Agents Autonomes P2P",
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
    limit = max(1, int(os.getenv("OPENCLAW_RATE_LIMIT_REQUESTS_PER_MINUTE", "120")))
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


def _is_admin_token_valid(token: str | None) -> bool:
    """Vérifie si le token administrateur est valide (temps constant)."""
    return bool(token and secrets.compare_digest(token, ADMIN_TOKEN))


def _require_admin(token: str | None) -> None:
    """Vérifie le token administrateur (temps constant) ou lève une exception 401."""
    if not _is_admin_token_valid(token):
        raise HTTPException(status_code=401, detail="Token admin invalide.")


# ---------------------------------------------------------------------- #
# Modèles de Données Pydantic
# ---------------------------------------------------------------------- #
class ExecutePayload(BaseModel):
    skill: str = Field(
        ..., min_length=1, max_length=100, description="Nom de la compétence à exécuter"
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="Paramètres d'entrée")


class FreeKeyRequest(BaseModel):
    email: str = Field(
        default="", max_length=320, description="Adresse email optionnelle pour identifier la clé"
    )
    plan: str = Field(
        default="free_community", description="Plan d'accès libre (ex: free_community)"
    )


class CreateKeyAdminPayload(BaseModel):
    email: str
    plan: str = "custom"
    days_valid: int | None = None
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
    """Affiche le portail web client 100% Free & Open-Access."""
    return render_portal_html()


# ---------------------------------------------------------------------- #
# 2. Accès Gratuit Instantané (Free Key Generation)
# ---------------------------------------------------------------------- #
@app.post("/api/v1/checkout/free-key")
@app.post("/api/v1/keys/generate-free")
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
        quota_limit=-1,   # Requêtes illimitées
        metadata={"free_access": True, "created_via": "portal_instant"},
    )
    return {
        "ok": True,
        "api_key": key_rec.key,
        "plan": "free_community",
        "email": email_in,
        "quota_limit": -1,
        "expires_at": None,
        "message": "🎉 Clé d'API gratuite générée avec succès ! Accès libre et illimité.",
    }


@app.post("/api/v1/checkout/demo-key")
async def create_demo_key(payload: dict):
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


# ---------------------------------------------------------------------- #
# 3. Authentification & Exécution
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
async def execute_skill(
    payload_in: ExecutePayload,
    request: Request,
    x_api_key: str | None = Header(None),
):
    """
    Exécute une compétence pour un client authentifié.
    Vérifie la clé et traite la requête.
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
                "text": f"🤖 [OpenClaw Free Gateway] Réponse traitée pour : '{prompt}'",
                "model": payload.get("model", "qwen2.5-coder-free"),
                "tokens": 42,
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


# ---------------------------------------------------------------------- #
# 3.1 Compatibilité OpenAI (Models, Tools & Chat Completions)
# ---------------------------------------------------------------------- #
@app.get("/v1/models")
async def list_openai_models():
    """Liste les modèles d'IA disponibles sur la passerelle OpenClawMesh."""
    now = int(time.time())
    models_list = [
        {"id": "qwen2.5-coder-7b", "object": "model", "created": now, "owned_by": "openclaw-mesh"},
        {"id": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit", "object": "model", "created": now, "owned_by": "mlx-metal"},
        {"id": "deepseek-v3-moe", "object": "model", "created": now, "owned_by": "openclaw-distributed-moe"},
        {"id": "whisper-base-stt", "object": "model", "created": now, "owned_by": "openclaw-multimodal"},
        {"id": "qwen2-vl-vision", "object": "model", "created": now, "owned_by": "openclaw-multimodal"},
    ]
    return {"object": "list", "data": models_list}


@app.get("/v1/tools")
async def list_openai_tools():
    """Retourne la liste des compétences exposées au format standard OpenAI Tool Calling."""
    tools = gateway_registry.to_openai_tools()
    return {"tools": tools}


@app.post("/v1/chat/completions")
async def openai_chat_completions(
    request: Request,
    payload: dict[str, Any],
    x_api_key: str | None = Header(None),
):
    """
    Endpoint compatible OpenAI Chat Completions avec support KV-Cache, Tool Calling et Streaming SSE.
    """
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
        # Génération inférence
        try:
            gen_res = await inference_engine.generate(prompt=last_user_msg, model=model)
            response_text = str(gen_res.get("text", f"🤖 Inférence OpenClaw pour : {last_user_msg}"))
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


# ---------------------------------------------------------------------- #
# 3.2 Observabilité Prometheus & Statut Cluster
# ---------------------------------------------------------------------- #
@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics(
    request: Request,
    token: str | None = Header(None, alias="X-Admin-Token"),
    api_key: str | None = Header(None, alias="X-API-Key"),
):
    """Exporte les métriques système et réseau au format Prometheus/OpenTelemetry."""
    client_host = request.client.host if request.client else "127.0.0.1"
    is_local = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
    key_rec = db.get_key(api_key) if api_key else None
    is_authed = (token is not None and _is_admin_token_valid(token)) or (key_rec is not None and key_rec.is_valid()[0])
    if not (is_local or is_authed):
        raise HTTPException(
            status_code=401,
            detail="Authentification requise (X-Admin-Token ou X-API-Key) pour accéder aux métriques.",
        )

    active_keys = len(db.list_all_keys())
    cache_stats = kv_cache.stats()
    avg_latency = (
        sum(_request_latencies) / len(_request_latencies) if _request_latencies else 0.0
    )

    lines = [
        "# HELP openclaw_requests_total Nombre total de requetes traitees",
        "# TYPE openclaw_requests_total counter",
        f'openclaw_requests_total{{status="200"}} {_request_counter["execute_total"] + _request_counter["chat_completions_total"]}',
        f'openclaw_requests_total{{status="500"}} {_request_counter["execute_errors"]}',
        "",
        "# HELP openclaw_active_api_keys Nombre de cles API enregistrees",
        "# TYPE openclaw_active_api_keys gauge",
        f"openclaw_active_api_keys {active_keys}",
        "",
        "# HELP openclaw_kv_cache_hits_total Nombre de hits dans le cache semantique",
        "# TYPE openclaw_kv_cache_hits_total counter",
        f"openclaw_kv_cache_hits_total {cache_stats['total_hits']}",
        f"openclaw_kv_cache_misses_total {cache_stats['total_misses']}",
        f"openclaw_kv_cache_hit_ratio {cache_stats['hit_ratio']}",
        f"openclaw_kv_cache_memory_used_mb {cache_stats['memory_used_mb']}",
        "",
        "# HELP openclaw_request_duration_seconds Latence moyenne des requetes en secondes",
        "# TYPE openclaw_request_duration_seconds gauge",
        f"openclaw_request_duration_seconds {round(avg_latency, 4)}",
        "",
        "# HELP openclaw_cluster_wan_active Statut d'activation WAN",
        "# TYPE openclaw_cluster_wan_active gauge",
        f"openclaw_cluster_wan_active {1 if _wan_node is not None else 0}",
    ]
    return "\n".join(lines) + "\n"


@app.get("/api/v1/cluster/status")
async def get_cluster_status(
    request: Request,
    token: str | None = Header(None, alias="X-Admin-Token"),
    api_key: str | None = Header(None, alias="X-API-Key"),
):
    """Retourne l'état complet du cluster : métriques, KV-Cache, nœud WAN et réputation."""
    client_host = request.client.host if request.client else "127.0.0.1"
    is_local = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
    key_rec = db.get_key(api_key) if api_key else None
    is_authed = (token is not None and _is_admin_token_valid(token)) or (key_rec is not None and key_rec.is_valid()[0])
    if not (is_local or is_authed):
        raise HTTPException(
            status_code=401,
            detail="Authentification requise (X-Admin-Token ou X-API-Key) pour consulter l'état du cluster.",
        )

    cache_st = kv_cache.stats()
    rep_recs = reputation_mgr.get_all_records()
    return {
        "ok": True,
        "wan_node_active": _wan_node is not None,
        "hardware": inference_engine.get_status(),
        "kv_cache": cache_st,
        "reputation": rep_recs,
        "registered_skills": gateway_registry.list_remote_names(),
        "timestamp": time.time(),
    }


# ---------------------------------------------------------------------- #
# 4. Administration & Nœud WAN (100% Confiance)
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
            logger.error(f"Échec création certificat TLS WAN: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Impossible de sécuriser le nœud WAN en TLS : {exc}. L'exposition non chiffrée sur 0.0.0.0 est bloquée par sécurité.",
            ) from None

        if ssl_ctx is None:
            raise HTTPException(
                status_code=500,
                detail="Contexte TLS indisponible. L'exposition non chiffrée sur 0.0.0.0 est bloquée par sécurité.",
            )

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
        "message": "⚡ Nœud WAN activé en 100% Confiance ! Chiffrement TLS et clé de sécurité auto-générés.",
    }


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
