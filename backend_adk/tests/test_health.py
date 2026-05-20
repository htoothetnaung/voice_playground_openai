"""Contains tests for health route test. in the backend."""
from fastapi.testclient import TestClient

from app.main import app


def test_health_route_returns_backend_status() -> None:
    """Verify this backend behavior stays stable for the call-center demo and its voice/runtime integrations."""
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "atenxion-callcenter-adk-backend"
    assert "voice_provider" in payload
    assert payload["available_architectures"] == ["cascaded_pipeline"]
    assert payload["llm_provider"] == "google_adk"
