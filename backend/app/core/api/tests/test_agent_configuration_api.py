"""HTTP contract for v0.10E-B Agent configuration and conversation display."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, ToolCall
from backend.app.main import app


class ToolUsingProvider(LLMProvider):
    """Call the calculator once, then answer with its result."""

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider="fake", model_name="fake-1", metadata={"configured": True}),)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if request.messages[-1].role.value == "tool":
            return LLMResponse(content="25 * 4 is 100.", model=request.model)
        return LLMResponse(
            content=None,
            model=request.model,
            tool_calls=(ToolCall(call_id="c1", name="calculator", arguments={"expression": "25 * 4"}),),
        )


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        test_client.app.state.service_registry.resolve(LLMProviderRegistry).register(ToolUsingProvider())
        yield test_client


def _create(client: TestClient, **overrides: object):
    body = {
        "name": "Calculator helper",
        "description": "Does arithmetic.",
        "type": "assistant",
        "llm_model": {"provider": "fake", "model_name": "fake-1"},
        "allowed_tools": ["calculator"],
        "instructions": "Use the calculator for arithmetic.",
        "initialize": True,
        **overrides,
    }
    return client.post("/api/agents", json=body)


def test_create_returns_ready_configured_agent(client: TestClient) -> None:
    response = _create(client)

    assert response.status_code == 201
    agent = response.json()
    assert agent["status"] == "idle"
    assert agent["allowed_tools"] == ["calculator"]
    assert agent["instructions"] == "Use the calculator for arithmetic."
    assert agent["llm_model"]["model_name"] == "fake-1"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"llm_model": {"provider": "nope", "model_name": "x"}}, "Unknown LLM provider 'nope'"),
        ({"llm_model": {"provider": "fake", "model_name": "fake-9"}}, "Model 'fake-9' is not available"),
        ({"allowed_tools": ["calculator", "rm_rf"]}, "Unknown tools: rm_rf"),
    ],
)
def test_invalid_configuration_is_rejected_before_creation(
    client: TestClient, overrides: dict[str, object], message: str
) -> None:
    response = _create(client, **overrides)

    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert client.get("/api/agents/count").json() == {"count": 0}


def test_configuration_patch_is_partial_and_validated(client: TestClient) -> None:
    agent_id = _create(client).json()["id"]

    updated = client.patch(f"/api/agents/{agent_id}/configuration", json={"allowed_tools": ["echo", "calculator"]})
    assert updated.status_code == 200
    assert updated.json()["allowed_tools"] == ["echo", "calculator"]
    assert updated.json()["instructions"] == "Use the calculator for arithmetic."

    assert client.patch(f"/api/agents/{agent_id}/configuration", json={}).status_code == 422
    assert client.patch(f"/api/agents/{agent_id}/configuration", json={"allowed_tools": None}).status_code == 422
    rejected = client.patch(f"/api/agents/{agent_id}/configuration", json={"allowed_tools": ["nope"]})
    assert rejected.status_code == 422
    assert "Unknown tools: nope" in rejected.json()["detail"]
    assert client.patch(f"/api/agents/{uuid4()}/configuration", json={"instructions": ""}).status_code == 404

    cleared = client.patch(f"/api/agents/{agent_id}/configuration", json={"llm_model": None})
    assert cleared.json()["llm_model"] is None


def test_chat_uses_allowed_tool_and_session_exposes_safe_tool_details(client: TestClient) -> None:
    agent_id = _create(client).json()["id"]

    chat = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Calculate 25 * 4"})

    assert chat.status_code == 200
    body = chat.json()
    assert body["response"]["content"] == "25 * 4 is 100."
    assert body["tool_activities"][0] | {"duration": None} == {
        "tool_name": "calculator",
        "status": "completed",
        "result": 100,
        "error": None,
        "duration": None,
    }
    messages = client.get(f"/api/agents/{agent_id}/session").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert {m["interaction_id"] for m in messages} == {body["interaction_id"]}
    assert messages[1]["tool_calls"] == ["calculator"]
    assert (messages[2]["tool_name"], messages[2]["tool_status"]) == ("calculator", "completed")
    assert "25 * 4" not in str(messages[1])  # tool-call arguments stay server-side


def test_disallowed_tool_is_rejected_by_the_safety_gate(client: TestClient) -> None:
    agent_id = _create(client, allowed_tools=["echo"]).json()["id"]

    chat = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Calculate 25 * 4"})

    assert chat.status_code == 200
    activity = chat.json()["tool_activities"][0]
    assert (activity["tool_name"], activity["status"], activity["error"]) == (
        "calculator",
        "rejected",
        "Requested tool is not allowed.",
    )
    assert client.get("/api/tools/history").json()["tasks"] == []


def test_chat_errors_explain_what_to_do(client: TestClient) -> None:
    no_model = _create(client, llm_model=None).json()["id"]
    response = client.post(f"/api/agents/{no_model}/chat", json={"message": "Hi"})
    assert response.status_code == 503
    assert "no model configured" in response.json()["detail"]

    not_ready = _create(client, initialize=False).json()["id"]
    response = client.post(f"/api/agents/{not_ready}/chat", json={"message": "Hi"})
    assert response.status_code == 409
    assert "isn't ready yet" in response.json()["detail"]

    unconfigured = _create(client, llm_model={"provider": "gemini", "model_name": _gemini_model(client)})
    if not _gemini_configured(client):
        response = client.post(f"/api/agents/{unconfigured.json()['id']}/chat", json={"message": "Hi"})
        assert response.status_code == 503
        assert "GEMINI_API_KEY" in response.json()["detail"]
        assert client.get(f"/api/agents/{unconfigured.json()['id']}/session").json()["messages"] == []


def _gemini_model(client: TestClient) -> str:
    return next(m["model_name"] for m in client.get("/api/llm/models").json()["models"] if m["provider"] == "gemini")


def _gemini_configured(client: TestClient) -> bool:
    return next(m for m in client.get("/api/llm/models").json()["models"] if m["provider"] == "gemini")["metadata"][
        "configured"
    ]
