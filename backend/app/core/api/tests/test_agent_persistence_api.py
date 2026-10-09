"""HTTP contract for v0.11 persistence: restarts, sessions, and storage failures."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.core_services.config.settings import settings
from backend.app.core.core_services.persistence import PersistenceError
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, ToolCall
from backend.app.database.migrations import DatabaseStartupError
from backend.app.main import app


class EchoingProvider(LLMProvider):
    """Use the calculator for arithmetic, otherwise report how much history it received."""

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider="fake", model_name="fake-1", metadata={"configured": True}),)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        last = request.messages[-1]
        if last.role.value == "tool":
            return LLMResponse(content="It is 100.", model=request.model)
        if "*" in last.content:
            return LLMResponse(
                content=None,
                model=request.model,
                tool_calls=(ToolCall(call_id="c1", name="calculator", arguments={"expression": "25 * 4"}),),
            )
        return LLMResponse(content=f"I received {len(request.messages)} messages.", model=request.model)


def started_client() -> TestClient:
    client = TestClient(app)
    client.__enter__()
    client.app.state.service_registry.resolve(LLMProviderRegistry).register(EchoingProvider())
    return client


def create_agent(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post(
        "/api/agents",
        json={
            "name": "Math helper",
            "description": "Arithmetic.",
            "type": "assistant",
            "llm_model": {"provider": "fake", "model_name": "fake-1"},
            "allowed_tools": ["calculator"],
            "instructions": "Use the calculator.",
            "initialize": True,
            **overrides,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_agents_configuration_and_conversations_survive_a_restart() -> None:
    client = started_client()
    agent = create_agent(client)
    agent_id = agent["id"]
    client.patch(f"/api/agents/{agent_id}/configuration", json={"allowed_tools": ["calculator", "echo"]})
    chat = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Calculate 25 * 4"}).json()
    client.__exit__(None, None, None)

    restarted = started_client()
    try:
        restored = restarted.get(f"/api/agents/{agent_id}").json()
        assert restored["status"] == "idle"
        assert restored["allowed_tools"] == ["calculator", "echo"]
        assert restored["instructions"] == "Use the calculator."
        assert restored["created_at"] == agent["created_at"]

        session = restarted.get(f"/api/agents/{agent_id}/session").json()
        assert session["id"] == chat["session_id"]
        assert [m["role"] for m in session["messages"]] == ["user", "assistant", "tool", "assistant"]
        assert session["messages"][1]["tool_calls"] == ["calculator"]
        assert "25 * 4" not in str(session["messages"][1])

        follow_up = restarted.post(f"/api/agents/{agent_id}/chat", json={"message": "Remember?"}).json()
        # system + 4 stored messages + the new user message
        assert follow_up["response"]["content"] == "I received 6 messages."
        assert follow_up["session_id"] == chat["session_id"]
    finally:
        restarted.__exit__(None, None, None)


def test_sessions_can_be_listed_started_and_resumed() -> None:
    with TestClient(app) as client:
        client.app.state.service_registry.resolve(LLMProviderRegistry).register(EchoingProvider())
        agent_id = create_agent(client)["id"]
        other_id = create_agent(client, name="Other")["id"]
        first_id = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Hello"}).json()["session_id"]

        started = client.post(f"/api/agents/{agent_id}/sessions")
        assert started.status_code == 201
        second_id = started.json()["id"]
        assert started.json()["messages"] == []
        fresh = client.post(f"/api/agents/{agent_id}/chat", json={"message": "New topic"}).json()
        assert fresh["session_id"] == second_id
        assert fresh["response"]["content"] == "I received 2 messages."

        resumed = client.post(
            f"/api/agents/{agent_id}/chat", json={"message": "Back again", "session_id": first_id}
        ).json()
        assert resumed["response"]["content"] == "I received 4 messages."

        listing = client.get(f"/api/agents/{agent_id}/sessions").json()
        assert listing["active_session_id"] == first_id
        assert [(s["id"], s["message_count"], s["title"]) for s in listing["sessions"]] == [
            (first_id, 4, "Hello"),
            (second_id, 2, "New topic"),
        ]
        assert client.get(f"/api/agents/{agent_id}/sessions/{second_id}").json()["messages"][0]["content"] == "New topic"

        assert client.get(f"/api/agents/{other_id}/sessions/{first_id}").status_code == 404
        assert client.post(f"/api/agents/{other_id}/chat", json={"message": "x", "session_id": first_id}).status_code == 404
        assert client.get(f"/api/agents/{agent_id}/sessions/{uuid4()}").status_code == 404
        assert client.get(f"/api/agents/{uuid4()}/sessions").status_code == 404

        client.post(f"/api/agents/{agent_id}/stop")
        assert client.post(f"/api/agents/{agent_id}/sessions").status_code == 409


def test_deleting_an_agent_removes_it_permanently() -> None:
    with TestClient(app) as client:
        agent_id = create_agent(client, llm_model=None)["id"]
        assert client.delete(f"/api/agents/{agent_id}").status_code == 200
    with TestClient(app) as restarted:
        assert restarted.get(f"/api/agents/{agent_id}").status_code == 404


def test_storage_failure_returns_503_and_leaves_no_partial_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as client:
        registry = client.app.state.service_registry.resolve(AgentRegistry)

        async def unavailable(_agent: object) -> None:
            raise PersistenceError("Genesis storage is unavailable. Try again shortly.")

        monkeypatch.setattr(registry._repository, "add", unavailable)
        response = client.post(
            "/api/agents", json={"name": "a", "description": "d", "type": "t"}
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "Genesis storage is unavailable. Try again shortly."
        assert client.get("/api/agents").json() == {"agents": []}


def test_startup_requires_a_migrated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")

    with pytest.raises(DatabaseStartupError, match="alembic upgrade head"):
        with TestClient(app):
            pass


def test_startup_failure_does_not_reveal_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://genesis:sup3r-secret@127.0.0.1:1/genesis")

    with pytest.raises(DatabaseStartupError) as caught:
        with TestClient(app):
            pass

    assert "sup3r-secret" not in str(caught.value)
    assert "Cannot connect to the Genesis database" in str(caught.value)
