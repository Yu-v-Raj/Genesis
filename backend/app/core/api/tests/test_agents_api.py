"""Read-only API tests for the Genesis Agent Runtime registry."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide an application client with the lifespan active."""
    with TestClient(app) as test_client:
        yield test_client


def test_agents_api_returns_empty_registry_and_count(client: TestClient) -> None:
    """The initial Agent Runtime API is read-only and empty."""
    assert client.get("/api/agents").json() == {"agents": []}
    assert client.get("/api/agents/count").json() == {"count": 0}


def test_agents_api_returns_registered_agent_and_not_found(client: TestClient) -> None:
    """The API serializes registered Agent records and returns 404 when absent."""
    registry = client.app.state.service_registry.resolve(AgentRegistry)
    agent = Agent(name="planner", description="Future planning process.", type="planning")
    client.portal.call(registry.register, agent)

    response = client.get(f"/api/agents/{agent.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(agent.id)
    assert response.json()["status"] == "created"
    assert client.get(f"/api/agents/{uuid4()}").status_code == 404


def test_agents_api_supports_lifecycle_metadata_and_context_operations(client: TestClient) -> None:
    """Phase B writes are thin adapters over the app-scoped Agent Manager."""
    created = client.post(
        "/api/agents",
        json={
            "name": "planner",
            "description": "Plans future work.",
            "type": "planning",
            "metadata": {"priority": "low"},
            "tags": ["test"],
        },
    )

    assert created.status_code == 201
    agent_id = created.json()["id"]
    assert client.get(f"/api/agents/{agent_id}/context").json()["current_state"] == "created"
    assert client.post(f"/api/agents/{agent_id}/initialize").json()["status"] == "idle"
    assert client.post(f"/api/agents/{agent_id}/start").json()["status"] == "running"
    assert client.post(f"/api/agents/{agent_id}/pause").json()["status"] == "paused"
    assert client.post(f"/api/agents/{agent_id}/resume").json()["status"] == "running"

    metadata = client.patch(f"/api/agents/{agent_id}/metadata", json={"metadata": {"priority": "high"}})
    context = client.patch(
        f"/api/agents/{agent_id}/context",
        json={
            "current_task": "prepare plan",
            "temporary_variables": {"attempt": 1},
            "runtime_metadata": {"worker": "local"},
        },
    )

    assert metadata.json()["metadata"] == {"priority": "high"}
    assert context.json()["current_task"] == "prepare plan"
    assert context.json()["temporary_variables"] == {"attempt": 1}
    assert context.json()["runtime_metadata"] == {"worker": "local"}
    assert client.post(f"/api/agents/{agent_id}/stop").json()["status"] == "stopped"
    assert client.delete(f"/api/agents/{agent_id}").status_code == 200
    assert client.get(f"/api/agents/{agent_id}").status_code == 404


def test_agents_api_rejects_invalid_lifecycle_transitions(client: TestClient) -> None:
    """Lifecycle policy violations produce a stable conflict response."""
    agent_id = client.post(
        "/api/agents",
        json={"name": "planner", "description": "Plans future work.", "type": "planning"},
    ).json()["id"]

    response = client.post(f"/api/agents/{agent_id}/start")

    assert response.status_code == 409
    assert "cannot transition" in response.json()["detail"]
