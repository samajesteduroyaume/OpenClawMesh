"""État partagé, dépendances et configuration pour la Passerelle OpenClawMesh."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Any

from fastapi import HTTPException, Header, Request, status
from pydantic import BaseModel, Field

from ..bridge import SkillRegistry
from ..client import MeshClient
from ..config import get_settings
from ..crypto import TrustStore
from ..engines.distributed_moe import DistributedMoEOrchestrator
from ..engines.inference import UniversalInferenceEngine
from ..engines.kv_cache import SemanticKVCache
from ..engines.multimodal import MultiModalEngine
from ..mcp_server import OpenClawMCPServer
from ..network.freebox_guichet import FreeboxGuichetClient
from ..node import OpenClawMeshNode
from ..reputation import ReputationManager
from .db import KeyDatabase

logger = logging.getLogger("openclaw_mesh.gateway")
_settings = get_settings()


# ---------------------------------------------------------------------- #
# Gestion du Jeton Admin
# ---------------------------------------------------------------------- #
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
        logger.warning("Jeton admin généré automatiquement pour la passerelle (NE PAS PARTAGER)")
        logger.warning("Fichier privé : %s", token_path)
        logger.warning("Pour une sécurité optimale, définissez GATEWAY_ADMIN_TOKEN explicitement")
        return token
    except OSError as exc:
        raise RuntimeError(
            "Impossible de créer le jeton admin. Définissez GATEWAY_ADMIN_TOKEN "
            "ou GATEWAY_ADMIN_TOKEN_FILE."
        ) from exc


ADMIN_TOKEN = _load_or_create_admin_token()
DEFAULT_DB_PATH = os.getenv("GATEWAY_DB_PATH", "openclaw_keys.db")

# Instance DB réelle — jamais le proxy, jamais server.db
_active_db: KeyDatabase = KeyDatabase(DEFAULT_DB_PATH)
_default_db = _active_db  # alias de compatibilité


def get_db() -> KeyDatabase:
    """Retourne la base de données active (jamais le proxy lui-même)."""
    return _active_db


def set_db(new_db: KeyDatabase) -> None:
    """Remplace la base de données active (monkeypatch pour les tests)."""
    global _active_db
    _active_db = new_db


class _DBProxy:
    """Proxy transparent déléguant à la DB active (sans récursion)."""

    def __getattr__(self, name: str) -> Any:
        # Appel direct à _active_db — aucun import de server.db
        return getattr(_active_db, name)


# Instance db exposée aux routes et au serveur
db = _DBProxy()

# Moteurs d'IA & Services de la passerelle
kv_cache = SemanticKVCache()
reputation_mgr = ReputationManager()
inference_engine = UniversalInferenceEngine()
moe_orchestrator = DistributedMoEOrchestrator()
multimodal_engine = MultiModalEngine()
mcp_service = OpenClawMCPServer(node_id="gateway-mcp-hub")
gateway_registry = SkillRegistry(name="gateway-engine")

_request_counter: dict[str, int] = defaultdict(int)
_request_latencies: deque[float] = deque(maxlen=500)
_demo_issued_emails: set[str] = set()

_wan_node: OpenClawMeshNode | None = None
guichet_client: FreeboxGuichetClient | None = None
mesh_client: MeshClient | None = None


# ---------------------------------------------------------------------- #
# Rate Limiting & Sécurité
# ---------------------------------------------------------------------- #
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


def _is_admin_token_valid(token: Any) -> bool:
    """Vérifie si le token administrateur est valide (temps constant)."""
    return bool(isinstance(token, str) and token and secrets.compare_digest(token, ADMIN_TOKEN))


def _require_admin(token: str | None, request: Request | None = None) -> None:
    """Vérifie le token administrateur (temps constant) ou autorise les requêtes locales."""
    if _is_admin_token_valid(token):
        return
    if request and request.client:
        client_host = request.client.host
        if client_host in {"127.0.0.1", "::1", "localhost", "testclient"}:
            return
    raise HTTPException(status_code=401, detail="Token admin invalide.")


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


# ---------------------------------------------------------------------- #
# Modèles Pydantic Partagés
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


class GuichetConnectPayload(BaseModel):
    guichet_url: str | None = Field(
        default=None, description="URL du Guichet Unique (ex: http://127.0.0.1:8790)"
    )


class MeshDispatchRequest(BaseModel):
    skill: str = Field(default="llm", description="Compétence demandée (ex: llm, vision, code)")
    prompt: str = Field(default="", description="Prompt ou requête pour le maillage")
    target_peer: str | None = Field(default=None, description="Nom ou adresse du pair ciblé")
    params: dict[str, Any] = Field(default_factory=dict, description="Paramètres d'inférence")


class ComparePayload(BaseModel):
    prompt: str = Field(..., description="Prompt envoyé en parallèle aux nœuds")
    targets: list[str] = Field(default=["apple_metal", "nvidia_cuda", "intel_npu"])


# ---------------------------------------------------------------------- #
# Contrôle du Nœud WAN
# ---------------------------------------------------------------------- #
async def start_wan_node(remote_access: bool = True) -> OpenClawMeshNode:
    """Démarre le nœud WAN en mode sécurisé."""
    global _wan_node
    if _wan_node is not None:
        return _wan_node

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
                detail=f"Impossible de sécuriser le nœud WAN en TLS : {exc}.",
            ) from None

        if ssl_ctx is None:
            raise HTTPException(
                status_code=500,
                detail="Contexte TLS indisponible pour sécuriser l'exposition WAN.",
            )

    node = OpenClawMeshNode(
        name=_settings.node_name,
        host="0.0.0.0" if remote_access else "127.0.0.1",
        port=_settings.default_port,
        registry=gateway_registry,
        psk=active_psk,
        trust_store=trust_store,
        ssl_context=ssl_ctx,
    )
    await node.start(enable_zeroconf=False)
    _wan_node = node
    return _wan_node


async def stop_wan_node() -> None:
    """Arrête le nœud WAN s'il est actif."""
    global _wan_node
    if _wan_node is not None:
        await _wan_node.stop()
        _wan_node = None


# ---------------------------------------------------------------------- #
# Cycle de Vie de la Passerelle (Lifespan)
# ---------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(_app: Any):
    global _wan_node, guichet_client, mesh_client
    try:
        # 1. Raccordement automatique au Guichet Unique pour les utilisateurs gratuits
        guichet_url = os.getenv("OPENCLAW_FREEBOX_GUICHET_URL") or _settings.freebox_guichet_url
        user_node_name = _settings.node_name or f"free-user-{secrets.token_hex(3)}"
        guichet_client = FreeboxGuichetClient(
            guichet_url=guichet_url,
            name=user_node_name,
            port=_settings.default_port,
            skills=["llm", "chat", "gateway", "inference", "free_community"],
        )
        try:
            detected = await guichet_client.detect_guichet_endpoint()
            if detected:
                logger.info(f"⚡ [Accès Gratuit] Raccordement au Guichet Unique Freebox : {detected}")
                await guichet_client.auto_onboard_first_start()
                guichet_client.start_heartbeat(interval=30.0)
            else:
                logger.info("ℹ️ Guichet Unique non joignable immédiatement (recherche en arrière-plan).")
        except Exception as exc:
            logger.debug(f"Auto-détection initiale du Guichet : {exc}")

        # 2. Démarrage du client Mesh pour consommer et interagir avec le maillage
        mesh_client = MeshClient(
            name=user_node_name,
            enable_discovery=True,
        )
        try:
            await mesh_client.start()
            if guichet_client and guichet_client.is_registered:
                await mesh_client.sync_guichet_peers()
        except Exception as exc:
            logger.debug(f"Démarrage initial MeshClient : {exc}")

        # 3. WAN Activé par Défaut
        if _settings.wan_enabled:
            try:
                await start_wan_node(remote_access=True)
                logger.info("🌐 [WAN Activé par Défaut] Nœud WAN démarré avec succès sur 0.0.0.0.")
            except Exception as exc:
                logger.debug(f"Démarrage initial nœud WAN (ignoré si port occupé) : {exc}")

        yield
    finally:
        if guichet_client:
            guichet_client.stop_heartbeat()
        if mesh_client:
            try:
                await mesh_client.stop()
            except Exception:
                pass
        if _wan_node is not None:
            await stop_wan_node()
