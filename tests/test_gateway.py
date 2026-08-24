import asyncio
import json
import time
import pytest
from fastapi.testclient import TestClient
from openclaw_mesh.gateway.db import KeyDatabase, KeyRecord
from openclaw_mesh.gateway.server import app, db


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_keys.db"
    return KeyDatabase(db_file)


def test_key_database_crud(temp_db):
    # 1. Create Key
    key_rec = temp_db.create_key(
        email="test@user.com",
        plan="pro_monthly",
        days_valid=30,
        quota_limit=100,
    )
    assert key_rec.key.startswith("sk_claw_")
    assert key_rec.email == "test@user.com"
    assert key_rec.quota_used == 0

    # 2. Get Key
    fetched = temp_db.get_key(key_rec.key)
    assert fetched is not None
    assert fetched.email == "test@user.com"
    valid, _ = fetched.is_valid()
    assert valid is True

    # 3. Increment Usage
    temp_db.increment_usage(key_rec.key, skill_name="llm", duration_ms=45.2)
    updated = temp_db.get_key(key_rec.key)
    assert updated.quota_used == 1

    # 4. Revocation
    temp_db.revoke_key(key_rec.key)
    revoked = temp_db.get_key(key_rec.key)
    valid_after_revoke, reason = revoked.is_valid()
    assert valid_after_revoke is False
    assert "révoquée" in reason


def test_key_quota_and_expiration(temp_db):
    # Expired key test
    expired_key = temp_db.create_key(
        email="expired@user.com",
        plan="trial",
        days_valid=0,  # Expired immediately
    )
    # Force expiration in past
    with temp_db._get_connection() as conn:
        conn.execute("UPDATE api_keys SET expires_at = ? WHERE key = ?", (time.time() - 100, expired_key.key))

    fetched_expired = temp_db.get_key(expired_key.key)
    valid, reason = fetched_expired.is_valid()
    assert valid is False
    assert "expirée" in reason

    # Quota limit test
    quota_key = temp_db.create_key(
        email="quota@user.com",
        plan="pack_10",
        quota_limit=2,
    )
    temp_db.increment_usage(quota_key.key)
    temp_db.increment_usage(quota_key.key)

    fetched_quota = temp_db.get_key(quota_key.key)
    valid_quota, reason_quota = fetched_quota.is_valid()
    assert valid_quota is False
    assert "Quota de requêtes épuisé" in reason_quota


def test_gateway_api_endpoints():
    client = TestClient(app)

    # 1. Test Portal HTML
    portal_resp = client.get("/portal")
    assert portal_resp.status_code == 200
    assert "Débloquez la Puissance d'OpenClawMesh" in portal_resp.text
    assert "Pro Mensuel" in portal_resp.text

    # 2. Test Demo Key Creation
    demo_resp = client.post("/api/v1/checkout/demo-key", json={"email": "demo_test@user.com"})
    assert demo_resp.status_code == 200
    demo_data = demo_resp.json()
    assert demo_data["ok"] is True
    demo_key = demo_data["api_key"]

    # 3. Verify Key Endpoint
    verify_resp = client.post("/api/v1/auth/verify", headers={"X-API-Key": demo_key})
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["valid"] is True
    assert v_data["plan"] == "demo_free"

    # 4. Execute Skill with Demo Key
    exec_resp = client.post(
        "/api/v1/execute",
        headers={"X-API-Key": demo_key},
        json={"skill": "echo", "payload": {"msg": "Hello Paid Mesh"}},
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["ok"] is True
    assert exec_data["result"] == {"msg": "Hello Paid Mesh"}

    # 5. Execute without Key -> 401
    unauth_resp = client.post("/api/v1/execute", json={"skill": "echo", "payload": {}})
    assert unauth_resp.status_code == 401

    # 6. Execute with Invalid Key -> 403
    bad_resp = client.post("/api/v1/execute", headers={"X-API-Key": "sk_claw_invalid_12345"}, json={"skill": "echo", "payload": {}})
    assert bad_resp.status_code == 403


def test_stripe_webhook_flow():
    client = TestClient(app)

    # Simuler un événement Stripe checkout.session.completed
    mock_stripe_event = {
        "id": f"evt_test_{int(time.time())}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_details": {
                    "email": "buyer_revolut@test.com",
                },
                "amount_total": 1000,
                "currency": "eur",
                "subscription": "sub_test_12345",
            }
        }
    }

    wh_resp = client.post("/api/webhooks/stripe", json=mock_stripe_event)
    assert wh_resp.status_code == 200
    wh_data = wh_resp.json()
    assert wh_data["status"] == "success"
    assert wh_data["action"] == "key_created"
    new_key = wh_data["api_key"]

    # Vérifier que la clé générée fonctionne immédiatement
    exec_resp = client.post(
        "/api/v1/execute",
        headers={"X-API-Key": new_key},
        json={"skill": "llm", "payload": {"prompt": "Write code"}},
    )
    assert exec_resp.status_code == 200
    assert exec_resp.json()["ok"] is True


def test_lifetime_license_flow():
    client = TestClient(app)

    # 1. Paiement Stripe Licence à Vie (200€ = 20000 centimes)
    mock_lifetime_event = {
        "id": f"evt_life_{int(time.time())}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_details": {
                    "email": "vip_lifetime@test.com",
                },
                "amount_total": 20000,
                "currency": "eur",
            }
        }
    }

    wh_resp = client.post("/api/webhooks/stripe", json=mock_lifetime_event)
    assert wh_resp.status_code == 200
    wh_data = wh_resp.json()
    assert wh_data["status"] == "success"
    lifetime_key = wh_data["api_key"]

    # 2. Vérifier que la clé est active et n'a AUCUNE date d'expiration (à vie)
    verify_resp = client.post("/api/v1/auth/verify", headers={"X-API-Key": lifetime_key})
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["valid"] is True
    assert v_data["plan"] == "lifetime"
    assert v_data["expires_at"] is None
