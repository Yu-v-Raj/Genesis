"""REST coverage for independent Execution Runtime endpoints."""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide an application client with its runtime lifespan active."""
    with TestClient(app) as test_client:
        yield test_client


def test_execution_api_creates_lists_cancels_and_validates_agent(client: TestClient) -> None:
    """The REST adapters expose queued work separately from Agent lifecycle operations."""
    created = client.post(
        "/api/agents", json={"name": "worker", "description": "Runs work.", "type": "test"}
    )
    agent_id = created.json()["id"]
    assert client.post(f"/api/agents/{agent_id}/execute", json={}).status_code == 409
    assert client.post(f"/api/agents/{agent_id}/initialize").status_code == 200

    response = client.post(f"/api/agents/{agent_id}/execute", json={"metadata": {"job": "x"}})
    assert response.status_code == 202
    execution_id = response.json()["execution_id"]
    assert response.json()["metadata"] == {"job": "x"}
    assert client.get("/api/executions").json()["executions"][0]["execution_id"] == execution_id
    assert client.get(f"/api/agents/{agent_id}/executions").status_code == 200
    assert client.post(f"/api/executions/{execution_id}/cancel").status_code == 200
    assert client.post(f"/api/executions/{execution_id}/cancel").status_code == 409
    assert client.get("/api/executions/not-a-uuid").status_code == 422
