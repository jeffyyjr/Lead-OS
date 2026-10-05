from fastapi.testclient import TestClient

from app.main import app


def test_agent_loop_does_not_repeat_customer_message():
    with TestClient(app) as client:
        lead = client.post("/api/demo/hvac").json()
        result = client.post(f"/api/leads/{lead['id']}/agent/loop").json()
    assert [step["action"] for step in result["steps"]] == ["offer_booking"]
