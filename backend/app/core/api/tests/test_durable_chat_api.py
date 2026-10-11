"""HTTP contract for durable chat executions (v0.13)."""

import time

from fastapi.testclient import TestClient

from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.exceptions import LLMProviderError
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, ToolCall
from backend.app.main import app


class CalculatorProvider(LLMProvider):
    """Calls the calculator once per turn; can be told to fail the next request."""

    def __init__(self) -> None:
        self.fail_next = False

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider="fake", model_name="fake-1", metadata={"configured": True}),)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if self.fail_next:
            self.fail_next = False
            raise LLMProviderError("The fake provider is down.")
        if request.messages[-1].role.value == "tool":
            return LLMResponse(content="25 * 4 is 100.", model=request.model)
        return LLMResponse(
            content=None,
            model=request.model,
            tool_calls=(ToolCall(call_id="call-1", name="calculator", arguments={"expression": "25 * 4"}),),
        )


def start(client: TestClient) -> tuple[CalculatorProvider, str]:
    provider = CalculatorProvider()
    client.app.state.service_registry.resolve(LLMProviderRegistry).register(provider)
    agent = client.post(
        "/api/agents",
        json={
            "name": "Math helper",
            "description": "Arithmetic.",
            "type": "assistant",
            "llm_model": {"provider": "fake", "model_name": "fake-1"},
            "allowed_tools": ["calculator"],
            "initialize": True,
        },
    ).json()
    return provider, agent["id"]


def wait_for(client: TestClient, execution_id: str, status: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while (body := client.get(f"/api/executions/{execution_id}").json())["status"] != status:
        assert time.monotonic() < deadline, f"stayed {body['status']}, expected {status}"
        time.sleep(0.02)
    return body


def test_a_chat_turn_is_a_durable_execution_correlated_everywhere() -> None:
    with TestClient(app) as client:
        _, agent_id = start(client)

        chat = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Calculate 25 * 4"})

        assert chat.status_code == 200
        body = chat.json()
        execution_id = body["execution_id"]
        assert execution_id == body["interaction_id"]
        assert body["response"]["content"] == "25 * 4 is 100."

        execution = client.get(f"/api/executions/{execution_id}").json()
        assert (execution["status"], execution["agent_id"]) == ("completed", agent_id)
        assert execution["metadata"] == {"kind": "chat", "message": "Calculate 25 * 4", "session_id": body["session_id"]}
        assert execution["result"]["output"] == "25 * 4 is 100."
        assert execution["retry"]["allowed"] is False  # finished work is never repeated
        assert execution["checkpoint"]["tools_started"] == [{"name": "calculator", "call_id": "call-1", "side_effects": False}]
        assert "25 * 4" not in str(execution["checkpoint"])  # tool arguments are not stored there

        timeline = [(t["to_status"], t["detail"]) for t in client.get(f"/api/executions/{execution_id}/history").json()["transitions"]]
        assert ("running", "checkpoint: tool:calculator") in timeline
        assert timeline[-1][0] == "completed"

        session = client.get(f"/api/agents/{agent_id}/session").json()
        assert {m["interaction_id"] for m in session["messages"]} == {execution_id}
        assert [task["execution_id"] for task in client.get("/api/tools/history").json()["tasks"]] == [execution_id]

        events = client.get("/api/events?limit=200").json()["events"]
        chat_events = {e["event_type"] for e in events if e["payload"].get("execution_id") == execution_id}
        assert {"execution.created", "execution.started", "execution.completed"} <= chat_events
        assert any(e["event_type"] == "execution.completed" and e["payload"].get("kind") == "chat" for e in events)
        assert any(e["event_type"] == "llm.requested" and e["payload"].get("interaction_id") == execution_id for e in events)


def test_failed_chat_is_recorded_and_retry_does_not_duplicate_turns() -> None:
    with TestClient(app) as client:
        provider, agent_id = start(client)
        provider.fail_next = True

        failed = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Calculate 25 * 4"})
        assert failed.status_code == 502
        executions = client.get(f"/api/agents/{agent_id}/executions").json()["executions"]
        assert len(executions) == 1
        record = executions[0]
        assert (record["status"], record["error_category"]) == ("failed", "provider_error")
        assert record["retry"] == {"allowed": True, "requires_acknowledgement": False, "reason": "Retrying starts a new attempt with the same input."}
        assert client.get(f"/api/agents/{agent_id}/session").json()["messages"] == []
        assert client.get(f"/api/agents/{agent_id}").json()["status"] == "idle"

        retried = client.post(f"/api/executions/{record['execution_id']}/retry", json={})
        assert retried.status_code == 202
        done = wait_for(client, retried.json()["execution_id"], "completed")
        assert (done["attempt"], done["retry_of"]) == (2, record["execution_id"])
        messages = client.get(f"/api/agents/{agent_id}/session").json()["messages"]
        assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant"]
        assert {m["interaction_id"] for m in messages} == {done["execution_id"]}

        assert client.post(f"/api/executions/{done['execution_id']}/retry", json={}).status_code == 409
        assert client.get(f"/api/executions/{record['execution_id']}").json()["status"] == "failed"


def test_rejected_requests_create_no_execution() -> None:
    with TestClient(app) as client:
        start(client)
        not_ready = client.post(
            "/api/agents",
            json={"name": "n", "description": "d", "type": "t", "llm_model": {"provider": "fake", "model_name": "fake-1"}},
        ).json()["id"]
        no_model = client.post("/api/agents", json={"name": "m", "description": "d", "type": "t", "initialize": True}).json()["id"]

        assert client.post(f"/api/agents/{not_ready}/chat", json={"message": "hi"}).status_code == 409
        assert client.post(f"/api/agents/{no_model}/chat", json={"message": "hi"}).status_code == 503
        for agent_id in (not_ready, no_model):
            assert client.get(f"/api/agents/{agent_id}/executions").json()["executions"] == []
