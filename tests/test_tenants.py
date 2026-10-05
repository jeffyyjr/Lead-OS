import pytest
from fastapi.testclient import TestClient

from app.main import app

ADMIN = {"X-Admin-Key": "test-admin-key"}
PLUMBER = {
    "tenant_id": "acme-plumbing",
    "business_name": "Acme Plumbing",
    "service_postal_codes": ["10001"],
    "booking_url": "https://acme.example/book",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    with TestClient(app) as client:
        yield client


def test_tenant_writes_require_admin_key(client):
    assert client.put("/api/tenants/acme-plumbing", json=PLUMBER).status_code == 401
    assert client.put("/api/tenants/acme-plumbing", json=PLUMBER, headers={"X-Admin-Key": "wrong"}).status_code == 401


def test_lead_uses_its_own_tenant_settings(client):
    assert client.put("/api/tenants/acme-plumbing", json=PLUMBER, headers=ADMIN).status_code == 200

    lead = {"tenant_id": "acme-plumbing", "name": "A", "phone": "+15555550020", "service_type": "leak", "urgency": "today",
            "property_type": "residential", "preferred_time": "today", "consent_to_contact": True}
    # 19054 is in the demo HVAC area but not Acme's.
    outside = client.post("/api/leads", json={**lead, "postal_code": "19054"}).json()
    assert outside["status"] == "lost"

    inside = client.post("/api/leads", json={**lead, "phone": "+15555550021", "postal_code": "10001"}).json()
    result = client.post(f"/api/leads/{inside['id']}/agent/run").json()
    assert result["agent_result"]["tools"]["booking"]["booking_url"] == "https://acme.example/book"


def test_unknown_tenant_is_rejected(client):
    response = client.post("/api/leads", json={"tenant_id": "nope", "name": "A", "phone": "+15555550022"})
    assert response.status_code == 404


def test_demo_tenant_is_seeded(client):
    assert client.get("/api/tenants/demo-hvac", headers=ADMIN).json()["business_name"] == "Demo HVAC Co."
