"""Memories are durable, used in chat context, and removed with their Agent (HTTP)."""

from fastapi.testclient import TestClient

from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, MessageRole
from backend.app.main import app


class EchoSystem(LLMProvider):
    """Replies with whatever system context it was given, so the test can see it."""

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider="fake", model_name="fake-1", metadata={"configured": True}),)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        system = "\n".join(m.content for m in request.messages if m.role is MessageRole.SYSTEM)
        return LLMResponse(content=system or "(no system context)", model=request.model)


def test_memory_survives_restart_reaches_the_model_and_is_deleted_with_the_agent() -> None:
    with TestClient(app) as client:
        agent_id = client.post(
            "/api/agents",
            json={"name": "a", "description": "d", "type": "t", "llm_model": None, "initialize": True},
        ).json()["id"]
        created = client.post(f"/api/agents/{agent_id}/memory", json={"content": "The user's name is Yuvraj.", "kind": "fact"})
        assert created.status_code == 201
        client.patch(f"/api/agents/{agent_id}/configuration", json={"llm_model": None})

    with TestClient(app) as restarted:
        restarted.app.state.service_registry.resolve(LLMProviderRegistry).register(EchoSystem())
        restarted.patch(f"/api/agents/{agent_id}/configuration", json={"llm_model": {"provider": "fake", "model_name": "fake-1"}})
        assert [m["content"] for m in restarted.get(f"/api/agents/{agent_id}/memory").json()["memories"]] == ["The user's name is Yuvraj."]

        reply = restarted.post(f"/api/agents/{agent_id}/chat", json={"message": "What's my name?"}).json()["response"]["content"]
        assert "(fact) The user's name is Yuvraj." in reply

        assert restarted.delete(f"/api/agents/{agent_id}").status_code == 200
        assert restarted.get("/api/memory").json()["memories"] == []
