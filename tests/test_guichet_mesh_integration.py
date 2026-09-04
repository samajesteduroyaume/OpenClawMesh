"""
Tests de Validation de l'Intégration Guichet Unique & Utilisation du Maillage P2P (Mode Gratuit).
"""

import pytest
from fastapi.testclient import TestClient

from openclaw_mesh.gateway.server import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_free_key_generation(client):
    """Vérifie que l'émission de clé d'accès gratuit fonctionne instantanément."""
    resp = client.post("/api/v1/checkout/free-key", json={"email": "free_tester@openclaw.mesh"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["plan"] == "free_community"
    assert data["quota_limit"] == -1
    assert data["api_key"].startswith("sk_claw_")


def test_guichet_status_endpoint(client):
    """Vérifie que l'état du Guichet Unique est exposé avec la mention d'accès gratuit."""
    resp = client.get("/api/v1/guichet/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["is_free_user"] is True
    assert "connected" in data


def test_mesh_peers_endpoint(client):
    """Vérifie la remontée de l'annuaire des machines du maillage."""
    resp = client.get("/api/v1/mesh/peers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "peers" in data
    assert isinstance(data["peers"], list)


def test_mesh_dispatch_endpoint(client):
    """Vérifie que le dispatch de tâche d'inférence vers le maillage P2P fonctionne."""
    resp = client.post(
        "/api/v1/mesh/dispatch",
        json={"skill": "llm", "prompt": "Bonjour le maillage", "params": {"model": "test-model"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "result" in data
    assert "target_node" in data
    assert "duration_ms" in data


def test_guichet_connect_endpoint(client):
    """Vérifie le déclenchement de la reconnexion au Guichet Unique."""
    resp = client.post(
        "/api/v1/guichet/connect",
        json={"guichet_url": "http://127.0.0.1:8790"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "ok" in data
    assert "connected" in data


def test_cluster_status_includes_guichet_and_peers(client):
    """Vérifie que l'état du cluster intègre le statut du Guichet Unique et le mode gratuit."""
    resp = client.get("/api/v1/cluster/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["is_free_user"] is True
    assert "guichet" in data
    assert "connected_peers_count" in data


def test_portal_html_guichet_banner(client):
    """Vérifie la présence du bandeau Guichet Unique et du répertoire des pairs dans le HTML du portail."""
    resp = client.get("/portal")
    assert resp.status_code == 200
    html = resp.text
    assert "Guichet Unique Freebox" in html
    assert "guichetBanner" in html
    assert "meshPeersTable" in html
    assert "chatTargetNode" in html
    assert "Accès Gratuit &amp; Souverain" in html or "Accès Gratuit" in html
