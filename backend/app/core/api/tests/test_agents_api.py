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
