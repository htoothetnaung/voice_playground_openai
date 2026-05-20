"""Contains tests for scenario metadata test. in the backend."""
from fastapi.testclient import TestClient

from app.main import app


def test_callcenter_scenario_metadata() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    client = TestClient(app)

    response = client.get("/api/v1/callcenter/scenario")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario_key"] == "callcenteragent"
    assert payload["company_name"] == "Atenxion"
    assert "callcenteragent" in payload["agents"]
    assert "billingAgent" in payload["agents"]
    assert "searchAtenxionKnowledgeBase" in payload["tools"]["supervisor"]
