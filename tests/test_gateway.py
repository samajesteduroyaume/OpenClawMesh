"""
Tests de la Passerelle d'Inférence et d'Accès Libre OpenClawMesh (100% Free & Open-Access).

Couvre : KeyDatabase CRUD, quotas & expiration,
         endpoints API (portail libre, génération instantanée de clés gratuites, auth, execute),
         gestion de nœud WAN (100% Confiance),
         administration des clés d'accès.
"""

import hashlib
import time

import pytest
from fastapi.testclient import TestClient

import openclaw_mesh.gateway.server as gateway_server
from openclaw_mesh.gateway.db import KeyDatabase
from openclaw_mesh.gateway.server import ADMIN_TOKEN, app


@pytest.fixture
def temp_db(tmp_path):
    return KeyDatabase(tmp_path / "test_keys.db")


@pytest.fixture(autouse=True)
def isolate_gateway_db(tmp_path, monkeypatch):
    test_db = KeyDatabase(tmp_path / "gateway_test.db")
    monkeypatch.setattr(gateway_server, "db", test_db)
    return test_db


# ─────────────────────────────────────────────────────────────────────────────
# Tests KeyDatabase
# ─────────────────────────────────────────────────────────────────────────────
def test_key_database_crud(temp_db):
    # 1. Création
    key_rec = temp_db.create_key(
        email="test@user.com",
        plan="free_community",
        days_valid=30,
        quota_limit=100,
    )
    assert key_rec.key.startswith("sk_claw_")
    assert key_rec.email == "test@user.com"
    assert key_rec.quota_used == 0

    # 2. Récupération
    fetched = temp_db.get_key(key_rec.key)
    assert fetched is not None
    assert fetched.email == "test@user.com"
    valid, _ = fetched.is_valid()
    assert valid is True

    # 3. Incrémentation quota
    temp_db.increment_usage(key_rec.key, skill_name="llm", duration_ms=45.2)
    updated = temp_db.get_key(key_rec.key)
    assert updated.quota_used == 1

    # 4. Révocation
    temp_db.revoke_key(key_rec.key)
    revoked = temp_db.get_key(key_rec.key)
    valid_after_revoke, reason = revoked.is_valid()
    assert valid_after_revoke is False
    assert "révoquée" in reason


def test_key_quota_and_expiration(temp_db):
    # Clé expirée
    expired_key = temp_db.create_key(
        email="expired@user.com",
        plan="trial",
        days_valid=1,
    )
    with temp_db._get_connection() as conn:
        conn.execute(
            "UPDATE api_keys SET expires_at = ? WHERE key_hash = ?",
            (time.time() - 100, hashlib.sha256(expired_key.key.encode()).hexdigest()),
        )
    fetched_expired = temp_db.get_key(expired_key.key)
    valid, reason = fetched_expired.is_valid()
    assert valid is False
    assert "expirée" in reason

    # Quota épuisé
    quota_key = temp_db.create_key(email="quota@user.com", plan="pack_2", quota_limit=2)
    temp_db.increment_usage(quota_key.key)
    temp_db.increment_usage(quota_key.key)
    fetched_quota = temp_db.get_key(quota_key.key)
    valid_quota, reason_quota = fetched_quota.is_valid()
    assert valid_quota is False
    assert "Quota de requêtes épuisé" in reason_quota


# ─────────────────────────────────────────────────────────────────────────────
# Tests Endpoints API Free & Open-Access
# ─────────────────────────────────────────────────────────────────────────────
def test_gateway_api_endpoints():
    client = TestClient(app)

    # 1. Portail HTML — rendu 100% Free & Open-Access
    portal_resp = client.get("/portal")
    assert portal_resp.status_code == 200
    assert "OpenClawMesh" in portal_resp.text
    assert "Gratuit" in portal_resp.text
    assert "Command Center" in portal_resp.text

    # 2. Génération de Clé Gratuite Instantanée
    free_resp = client.post("/api/v1/checkout/free-key", json={"email": "community@user.com"})
    assert free_resp.status_code == 200
    free_data = free_resp.json()
    assert free_data["ok"] is True
    assert free_data["api_key"].startswith("sk_claw_")
    assert free_data["plan"] == "free_community"
    free_key = free_data["api_key"]

    # 3. Clé démo
    demo_resp = client.post("/api/v1/checkout/demo-key", json={"email": "demo_test@user.com"})
    assert demo_resp.status_code == 200
    demo_data = demo_resp.json()
    assert demo_data["ok"] is True
    demo_key = demo_data["api_key"]

    # 4. Vérification de clé gratuite
    verify_resp = client.post("/api/v1/auth/verify", headers={"X-API-Key": free_key})
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["valid"] is True
    assert v_data["plan"] == "free_community"

    # 5. Exécution avec clé gratuite
    exec_resp = client.post(
        "/api/v1/execute",
        headers={"X-API-Key": free_key},
        json={"skill": "echo", "payload": {"msg": "Hello Free Mesh"}},
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["ok"] is True
    assert exec_data["result"] == {"msg": "Hello Free Mesh"}

    # 6. Exécution LLM avec clé démo
    exec_llm = client.post(
        "/api/v1/execute",
        headers={"X-API-Key": demo_key},
        json={"skill": "llm", "payload": {"prompt": "Qu'est-ce qu'OpenClawMesh ?"}},
    )
    assert exec_llm.status_code == 200
    llm_data = exec_llm.json()
    assert llm_data["ok"] is True
    assert "OpenClaw Free Gateway" in llm_data["result"]["text"]

    # 7. Sans clé → 401
    unauth_resp = client.post("/api/v1/execute", json={"skill": "echo", "payload": {}})
    assert unauth_resp.status_code == 401

    # 8. Clé invalide → 403
    bad_resp = client.post(
        "/api/v1/execute",
        headers={"X-API-Key": "sk_claw_totally_invalid"},
        json={"skill": "echo", "payload": {}},
    )
    assert bad_resp.status_code == 403


def test_admin_key_management_flow():
    client = TestClient(app)

    # 1. Admin crée une clé
    create_resp = client.post(
        "/api/v1/admin/keys/create",
        headers={"X-Admin-Token": ADMIN_TOKEN},
        json={"email": "custom_admin@user.com", "plan": "vip_free", "quota_limit": 500},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["ok"] is True
    created_key = created["key"]["key"]

    # 2. Liste des clés (admin)
    list_resp = client.get(
        "/api/v1/admin/keys",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert list_resp.status_code == 200
    keys_data = list_resp.json()
    assert keys_data["count"] >= 1

    # 3. Révocation par admin
    revoke_resp = client.delete(
        f"/api/v1/admin/keys/{created_key}",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["ok"] is True

    # 4. Vérification que la clé révoquée est refusée
    verify_resp = client.post("/api/v1/auth/verify", headers={"X-API-Key": created_key})
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is False


@pytest.mark.asyncio
async def test_admin_wan_toggle_100_percent_confidence():
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Activer le nœud WAN en 100% Confiance sans PSK préexistante
        activate_resp = await client.post(
            "/api/v1/admin/wan/toggle",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"remote_access": True},
        )
        assert activate_resp.status_code == 200
        act_data = activate_resp.json()
        assert act_data["ok"] is True
        assert act_data["active"] is True
        assert act_data["host"] == "0.0.0.0"
        assert "psk" in act_data
        assert "connect_url" in act_data
        assert "cli_command" in act_data

        # 2. Désactiver le nœud WAN (retour en local)
        deactivate_resp = await client.post(
            "/api/v1/admin/wan/toggle",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"remote_access": False},
        )
        assert deactivate_resp.status_code == 200
        deact_data = deactivate_resp.json()
        assert deact_data["ok"] is True
        assert deact_data["active"] is False


def test_prometheus_metrics_endpoint():
    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "openclaw_requests_total" in resp.text
    assert "openclaw_kv_cache_hits_total" in resp.text


def test_openai_models_and_tools_endpoints():
    client = TestClient(app)

    # 1. Modèles
    m_resp = client.get("/v1/models")
    assert m_resp.status_code == 200
    models_data = m_resp.json()
    assert "data" in models_data
    assert len(models_data["data"]) >= 1

    # 2. Outils
    t_resp = client.get("/v1/tools")
    assert t_resp.status_code == 200
    assert "tools" in t_resp.json()


def test_openai_chat_completions_with_kv_cache():
    client = TestClient(app)

    # 1. Créer une clé gratuite
    key_resp = client.post("/api/v1/checkout/free-key", json={"email": "chat_tester@example.com"})
    api_key = key_resp.json()["api_key"]

    prompt = "Bonjour OpenClaw, quel est ton protocole ?"
    # 2. Premier appel (Cache Miss)
    resp1 = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "qwen2.5-coder-7b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "choices" in data1
    assert data1["kv_cache_hit"] is False

    # 3. Deuxième appel identique (Cache Hit)
    resp2 = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "qwen2.5-coder-7b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["kv_cache_hit"] is True


def test_cluster_status_endpoint():
    client = TestClient(app)
    resp = client.get("/api/v1/cluster/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "hardware" in data
    assert "kv_cache" in data
    assert "reputation" in data

