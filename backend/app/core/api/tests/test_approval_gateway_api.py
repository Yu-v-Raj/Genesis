"""Milestone 2 end to end: a consequential tool call pauses, the operator decides, and the
exact operation runs once or not at all, for Agent chats, workflow steps and operator tests.

Real application wiring and a freshly migrated database per test. The only "side effect"
is ``simulated_action``, which does nothing outside Genesis.
"""

import json
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, ToolCall
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.domain.tool import Tool
from backend.app.core.tool_runtime.domain.tool_metadata import ToolMetadata
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus
from backend.app.core.workflow_runtime.application.workflow_manager import WorkflowManager
from backend.app.main import app


CONSOLE = {"Origin": "http://localhost:3000"}


class ActionProvider(LLMProvider):
    """Asks for ``simulated_action`` (once per tool call listed), then reports what the tool said."""

    def __init__(self, *calls: dict[str, object]) -> None:
        self.calls = calls or ({"note": "hello"},)
        self.requests: list[LLMRequest] = []

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider="fake", model_name="fake-1", metadata={"configured": True}),)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if request.messages[-1].role.value == "tool":
            results = [json.loads(m.content) for m in request.messages if m.role.value == "tool"]
            return LLMResponse(content=f"Tool said: {json.dumps(results)}", model=request.model)
        return LLMResponse(
            content=None,
            model=request.model,
            tool_calls=tuple(
                ToolCall(call_id=f"call-{index}", name="simulated_action", arguments=arguments)
                for index, arguments in enumerate(self.calls)
            ),
        )


def agent(client: TestClient, provider: LLMProvider, tools: list[str] | None = None) -> str:
    client.app.state.service_registry.resolve(LLMProviderRegistry).register(provider)
    created = client.post(
        "/api/agents",
        json={
            "name": "Courier",
            "description": "Sends things.",
            "type": "assistant",
            "llm_model": {"provider": "fake", "model_name": "fake-1"},
            "allowed_tools": tools if tools is not None else ["simulated_action"],
            "initialize": True,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def wait(client: TestClient, path: str, *statuses: str, key: str = "status", timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while (body := client.get(path).json())[key] not in statuses:
        assert time.monotonic() < deadline, f"{path} stayed {body[key]}"
        time.sleep(0.02)
    return body


def runs_of(client: TestClient, tool: str = "simulated_action") -> list[dict]:
    return [task for task in client.get("/api/tools/history").json()["tasks"] if task["tool_name"] == tool]


def approval(client: TestClient, approval_id: str) -> dict:
    return client.get(f"/api/approvals/{approval_id}").json()


# ----------------------------------------------------------------- Agent chats


def test_an_agent_turn_waits_then_runs_the_exact_call_once_after_approval() -> None:
    with TestClient(app) as client:
        provider = ActionProvider({"note": "hello"})
        agent_id = agent(client, provider)

        held = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Please do it."})
        assert held.status_code == 202, held.text
        body = held.json()
        assert body["status"] == "waiting_approval"
        execution = client.get(f"/api/executions/{body['execution_id']}").json()
        assert execution["status"] == "waiting_approval" and "pending_turn" not in execution["checkpoint"]
        assert runs_of(client) == []
        assert client.get(f"/api/agents/{agent_id}").json()["status"] == "idle"

        request = approval(client, body["approval_id"])
        assert request["state"] == "pending" and request["caller"] == "agent" and request["can_decide"]
        assert request["subject"]["agent_name"] == "Courier" and request["subject"]["execution_id"] == body["execution_id"]
        assert request["arguments"] == {"note": "hello"} and request["redacted_fields"] == []
        assert request["tool_description"].startswith("Simulates an external action")
        assert [item["approval_id"] for item in client.get("/api/approvals", params={"state": "pending"}).json()["approvals"]] == [body["approval_id"]]

        busy = client.post(f"/api/agents/{agent_id}/chat", json={"message": "And another."})
        assert busy.status_code == 409 and "Approvals" in busy.json()["detail"]

        decided = client.post(f"/api/approvals/{body['approval_id']}/approve", headers=CONSOLE)
        assert decided.status_code == 200 and decided.json()["approval"]["decision_source"] == "local_operator_console"
        done = wait(client, f"/api/executions/{body['execution_id']}", "completed", "failed")
        assert done["status"] == "completed" and "Simulated only" in done["result"]["output"]

        (task,) = runs_of(client)
        assert task["metadata"]["approval_id"] == body["approval_id"] and task["metadata"]["agent_id"] == agent_id
        final = approval(client, body["approval_id"])
        assert (final["state"], final["outcome"], final["task_id"]) == ("consumed", "completed", task["task_id"])
        session = client.get(f"/api/agents/{agent_id}/session").json()
        assert [m["role"] for m in session["messages"]] == ["user", "assistant", "tool", "assistant"]
        assert client.post(f"/api/approvals/{body['approval_id']}/approve", headers=CONSOLE).status_code == 409
        assert len(runs_of(client)) == 1


def test_a_rejected_call_never_runs_and_the_model_is_told() -> None:
    with TestClient(app) as client:
        provider = ActionProvider({"note": "nope"})
        agent_id = agent(client, provider)
        body = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Do it."}).json()

        assert client.post(f"/api/approvals/{body['approval_id']}/reject", headers=CONSOLE).status_code == 200
        done = wait(client, f"/api/executions/{body['execution_id']}", "completed", "failed")

        assert done["status"] == "completed" and "rejected this tool call" in done["result"]["output"]
        assert runs_of(client) == [] and approval(client, body["approval_id"])["state"] == "rejected"


def test_a_changed_allowlist_while_waiting_prevents_the_call() -> None:
    with TestClient(app) as client:
        provider = ActionProvider()
        agent_id = agent(client, provider)
        body = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Do it."}).json()

        changed = client.patch(f"/api/agents/{agent_id}/configuration", json={"allowed_tools": ["echo"]})
        assert changed.status_code == 200, changed.text
        client.post(f"/api/approvals/{body['approval_id']}/approve", headers=CONSOLE)
        done = wait(client, f"/api/executions/{body['execution_id']}", "completed", "failed")

        assert done["status"] == "completed" and "not allowed" in done["result"]["output"]
        assert runs_of(client) == []
        final = approval(client, body["approval_id"])
        assert final["state"] == "cancelled" and final["detail"].startswith("Not run")


def test_cancelling_a_waiting_turn_cancels_its_request() -> None:
    with TestClient(app) as client:
        agent_id = agent(client, ActionProvider())
        body = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Do it."}).json()

        cancelled = client.post(f"/api/executions/{body['execution_id']}/cancel")
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        assert approval(client, body["approval_id"])["state"] == "cancelled"
        assert client.post(f"/api/approvals/{body['approval_id']}/approve", headers=CONSOLE).status_code == 409
        assert runs_of(client) == []
        assert client.post(f"/api/agents/{agent_id}/chat", json={"message": "Next."}).status_code == 202  # free again


def test_repeated_identical_calls_need_separate_decisions() -> None:
    with TestClient(app) as client:
        agent_id = agent(client, ActionProvider({"note": "same"}, {"note": "same"}))
        body = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Twice."}).json()

        client.post(f"/api/approvals/{body['approval_id']}/approve", headers=CONSOLE)
        wait(client, f"/api/approvals/{body['approval_id']}", "consumed", key="state")
        deadline = time.monotonic() + 5
        while not (pending := client.get("/api/approvals", params={"state": "pending"}).json()["approvals"]):
            assert time.monotonic() < deadline, "the second identical call never asked for approval"
            time.sleep(0.02)
        second = wait(client, f"/api/executions/{body['execution_id']}", "waiting_approval", "completed")
        assert second["status"] == "waiting_approval" and len(runs_of(client)) == 1
        assert len(pending) == 1 and pending[0]["approval_id"] != body["approval_id"]

        client.post(f"/api/approvals/{pending[0]['approval_id']}/reject", headers=CONSOLE)
        wait(client, f"/api/executions/{body['execution_id']}", "completed")
        assert len(runs_of(client)) == 1


def test_a_waiting_turn_survives_a_restart_and_does_not_run_on_its_own() -> None:
    with TestClient(app) as client:
        agent_id = agent(client, ActionProvider())
        body = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Do it."}).json()

    with TestClient(app) as restarted:
        restarted.app.state.service_registry.resolve(LLMProviderRegistry).register(ActionProvider())
        time.sleep(0.2)
        assert restarted.get(f"/api/executions/{body['execution_id']}").json()["status"] == "waiting_approval"
        assert approval(restarted, body["approval_id"])["state"] == "pending"
        assert runs_of(restarted) == []

        restarted.post(f"/api/approvals/{body['approval_id']}/approve", headers=CONSOLE)
        done = wait(restarted, f"/api/executions/{body['execution_id']}", "completed", "failed")
        assert done["status"] == "completed" and len(runs_of(restarted)) == 1


# --------------------------------------------------------------- workflow steps


def flow(client: TestClient) -> str:
    definition = client.post(
        "/api/workflow-definitions",
        json={
            "name": "Notify",
            "tasks": [
                {"task_id": "send", "name": "Send", "tool_name": "simulated_action", "tool_arguments": {"note": "deploy done"}},
                {"task_id": "after", "name": "After", "tool_name": "echo", "tool_arguments": {"message": "sent"}, "dependencies": ["send"]},
                {"task_id": "other", "name": "Independent", "tool_name": "echo", "tool_arguments": {"message": "meanwhile"}},
            ],
        },
    )
    assert definition.status_code == 201, definition.text
    run = client.post(f"/api/workflow-definitions/{definition.json()['definition_id']}/runs", json={}).json()
    client.post(f"/api/workflows/{run['workflow_id']}/start")
    return run["workflow_id"]


def steps(run: dict) -> dict[str, dict]:
    return {task["task_id"]: task for task in run["tasks"]}


def test_a_workflow_step_waits_and_its_dependents_wait_with_it() -> None:
    with TestClient(app) as client:
        run_id = flow(client)
        waiting = wait(client, f"/api/workflows/{run_id}", "waiting_approval", "completed", "failed")

        by_id = steps(waiting)
        assert waiting["status"] == "waiting_approval"
        assert by_id["send"]["status"] == "waiting_approval" and by_id["send"]["approval_id"]
        assert by_id["other"]["status"] == "completed" and by_id["after"]["status"] == "pending"
        assert runs_of(client) == []
        request = approval(client, by_id["send"]["approval_id"])
        assert request["caller"] == "workflow" and request["subject"]["workflow_name"] == "Notify"
        assert (request["subject"]["step_id"], request["subject"]["step_name"], request["subject"]["attempt"]) == ("send", "Send", 1)
        assert "agent_id" not in {k for k, v in request["subject"].items() if v}

        client.post(f"/api/approvals/{by_id['send']['approval_id']}/approve", headers=CONSOLE)
        done = wait(client, f"/api/workflows/{run_id}", "completed", "failed")

        assert done["status"] == "completed" and steps(done)["after"]["status"] == "completed"
        (task,) = runs_of(client)
        assert task["metadata"]["workflow_id"] == run_id and task["metadata"]["approval_id"] == by_id["send"]["approval_id"]
        # Duplicate notifications or decisions change nothing.
        manager = client.app.state.service_registry.resolve(WorkflowManager)
        client.portal.call(manager.resume_ready)
        assert client.post(f"/api/approvals/{by_id['send']['approval_id']}/approve", headers=CONSOLE).status_code == 409
        assert len(runs_of(client)) == 1


def test_a_rejected_step_fails_the_run_and_blocks_its_dependents() -> None:
    with TestClient(app) as client:
        run_id = flow(client)
        waiting = wait(client, f"/api/workflows/{run_id}", "waiting_approval")

        client.post(f"/api/approvals/{steps(waiting)['send']['approval_id']}/reject", headers=CONSOLE)
        done = wait(client, f"/api/workflows/{run_id}", "failed", "completed")

        by_id = steps(done)
        assert (by_id["send"]["status"], by_id["after"]["status"], by_id["other"]["status"]) == ("failed", "blocked", "completed")
        assert "rejected" in by_id["send"]["error"] and runs_of(client) == []
        # A retry is a new attempt: the old decision can't be reused, a new request opens.
        retried = client.post(f"/api/workflows/{run_id}/retry", json={})
        assert retried.status_code == 200, retried.text
        again = wait(client, f"/api/workflows/{run_id}", "waiting_approval")
        assert steps(again)["send"]["approval_id"] != steps(waiting)["send"]["approval_id"]
        assert approval(client, steps(again)["send"]["approval_id"])["subject"]["attempt"] == 2


def test_cancelling_a_waiting_run_cancels_its_request() -> None:
    with TestClient(app) as client:
        run_id = flow(client)
        approval_id = steps(wait(client, f"/api/workflows/{run_id}", "waiting_approval"))["send"]["approval_id"]

        assert client.post(f"/api/workflows/{run_id}/cancel").status_code == 200
        assert approval(client, approval_id)["state"] == "cancelled"
        assert client.post(f"/api/approvals/{approval_id}/approve", headers=CONSOLE).status_code == 409
        assert runs_of(client) == []


def test_a_waiting_run_survives_a_restart_without_running() -> None:
    with TestClient(app) as client:
        run_id = flow(client)
        approval_id = steps(wait(client, f"/api/workflows/{run_id}", "waiting_approval"))["send"]["approval_id"]

    with TestClient(app) as restarted:
        time.sleep(0.2)
        assert restarted.get(f"/api/workflows/{run_id}").json()["status"] == "waiting_approval"
        assert runs_of(restarted) == []
        restarted.post(f"/api/approvals/{approval_id}/approve", headers=CONSOLE)
        assert wait(restarted, f"/api/workflows/{run_id}", "completed", "failed")["status"] == "completed"
        assert len(runs_of(restarted)) == 1


# --------------------------------------------------------------- operator tests


def test_an_operator_test_of_a_side_effect_waits_then_runs_once() -> None:
    with TestClient(app) as client:
        held = client.post("/api/tools/execute", json={"tool_name": "simulated_action", "arguments": {"note": "try"}}, headers=CONSOLE)
        repeat = client.post("/api/tools/execute", json={"tool_name": "simulated_action", "arguments": {"note": "try"}}, headers=CONSOLE)

        assert held.status_code == 202 and held.json()["outcome"] == "approval_required"
        assert repeat.json()["approval_id"] == held.json()["approval_id"]  # a double submit opens one request
        assert runs_of(client) == []
        approval_id = held.json()["approval_id"]
        assert approval(client, approval_id)["caller"] == "operator"

        approved = client.post(f"/api/approvals/{approval_id}/approve", headers=CONSOLE)
        assert approved.status_code == 200
        assert approved.json()["task"]["result"]["output"] == "Simulated only; nothing left Genesis: try"
        assert approved.json()["approval"]["state"] == "consumed"
        assert client.post(f"/api/approvals/{approval_id}/approve", headers=CONSOLE).status_code == 409
        assert client.post(f"/api/approvals/{approval_id}/run", headers=CONSOLE).status_code == 409
        assert len(runs_of(client)) == 1


def test_an_operator_cannot_forge_an_approval_and_rejection_runs_nothing() -> None:
    with TestClient(app) as client:
        forged = client.post(
            "/api/tools/execute",
            json={"tool_name": "simulated_action", "arguments": {"note": "x"}, "metadata": {"approval_id": str(uuid4()), "approved": True}},
            headers=CONSOLE,
        )
        assert forged.status_code == 202

        client.post(f"/api/approvals/{forged.json()['approval_id']}/reject", headers=CONSOLE)
        assert approval(client, forged.json()["approval_id"])["state"] == "rejected"
        assert runs_of(client) == []


def test_approval_actions_are_protected_like_every_other_state_change() -> None:
    with TestClient(app) as client:
        held = client.post("/api/tools/execute", json={"tool_name": "simulated_action", "arguments": {"note": "x"}}).json()

        cross_site = client.post(f"/api/approvals/{held['approval_id']}/approve", headers={"Origin": "https://evil.example"})
        rebinding = client.post(f"/api/approvals/{held['approval_id']}/approve", headers={"Host": "attacker.example"})
        assert (cross_site.status_code, rebinding.status_code) == (403, 400)
        assert approval(client, held["approval_id"])["state"] == "pending"
        assert client.get(f"/api/approvals/{uuid4()}").status_code == 404
        assert client.post(f"/api/approvals/{uuid4()}/approve", headers=CONSOLE).status_code == 404
        assert client.get("/api/approvals/not-a-uuid").status_code == 422
        api_client = client.post(f"/api/approvals/{held['approval_id']}/reject")  # local script, no Origin
        assert api_client.json()["approval"]["decision_source"] == "local_api_client"


@pytest.mark.parametrize("tool", ["simulated_action"])
def test_approval_events_never_carry_arguments(tool: str) -> None:
    with TestClient(app) as client:
        held = client.post("/api/tools/execute", json={"tool_name": tool, "arguments": {"note": "secret-note-value"}}, headers=CONSOLE).json()
        client.post(f"/api/approvals/{held['approval_id']}/approve", headers=CONSOLE)

        events = [e for e in client.get("/api/events", params={"limit": 1000}).json()["events"] if e["event_type"].startswith("approval.")]
        assert {e["event_type"] for e in events} >= {"approval.requested", "approval.approved", "approval.consumed", "approval.outcome"}
        assert "secret-note-value" not in json.dumps(events)


def test_secret_looking_arguments_are_redacted_for_display_but_bound_exactly() -> None:
    with TestClient(app) as client:
        received: list[dict] = []

        async def handler(request):
            received.append(dict(request.arguments))
            return ToolResult(status=ToolResultStatus.COMPLETED, output="ok")

        tools = client.app.state.service_registry.resolve(ToolRuntimeManager)
        client.portal.call(
            tools.register,
            Tool(
                definition=ToolMetadata(
                    name="post_webhook",
                    description="Posts to a webhook (test double).",
                    side_effects=True,
                    parameters={"type": "object", "properties": {"url": {"type": "string"}, "api_key": {"type": "string"}}, "required": ["url", "api_key"]},
                ),
                handler=handler,
            ),
        )
        held = client.post("/api/tools/execute", json={"tool_name": "post_webhook", "arguments": {"url": "https://example.test", "api_key": "k-123"}}).json()

        shown = approval(client, held["approval_id"])
        assert shown["arguments"] == {"url": "https://example.test", "api_key": "[redacted]"} and shown["redacted_fields"] == ["api_key"]
        assert "k-123" not in json.dumps(client.get("/api/approvals").json())
        client.post(f"/api/approvals/{held['approval_id']}/approve", headers=CONSOLE)
        assert received == [{"url": "https://example.test", "api_key": "k-123"}]  # the exact approved value


# ------------------------------------------------------- expiry and state changes


@pytest.fixture
def fast_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short approval lifetime and worker tick so expiry is observed within the test."""
    from backend.app.core.core_services.config.settings import settings

    monkeypatch.setattr(settings, "APPROVAL_TTL_SECONDS", 0.3)
    monkeypatch.setattr(settings, "WORKER_LEASE_SECONDS", 0.3)


def test_an_expired_request_never_runs_and_the_turn_continues(fast_clock: None) -> None:
    with TestClient(app) as client:
        agent_id = agent(client, ActionProvider())
        body = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Do it."}).json()

        done = wait(client, f"/api/executions/{body['execution_id']}", "completed", "failed")

        assert done["status"] == "completed" and "expired" in done["result"]["output"]
        assert approval(client, body["approval_id"])["state"] == "expired"
        assert client.post(f"/api/approvals/{body['approval_id']}/approve", headers=CONSOLE).status_code == 409
        assert runs_of(client) == []


def test_an_expired_step_request_fails_the_step(fast_clock: None) -> None:
    with TestClient(app) as client:
        run_id = flow(client)
        done = wait(client, f"/api/workflows/{run_id}", "failed", "completed", timeout=8)

        assert "expired" in steps(done)["send"]["error"] and runs_of(client) == []


def test_stopping_the_agent_while_waiting_prevents_the_call() -> None:
    with TestClient(app) as client:
        agent_id = agent(client, ActionProvider())
        body = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Do it."}).json()

        assert client.post(f"/api/agents/{agent_id}/stop").status_code == 200
        client.post(f"/api/approvals/{body['approval_id']}/approve", headers=CONSOLE)
        done = wait(client, f"/api/executions/{body['execution_id']}", "completed", "failed")

        assert done["status"] == "failed" and done["error_category"] == "agent_unavailable"
        assert approval(client, body["approval_id"])["state"] == "cancelled"
        assert runs_of(client) == []


def test_disabling_the_tool_while_waiting_prevents_the_call() -> None:
    with TestClient(app) as client:
        agent_id = agent(client, ActionProvider())
        body = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Do it."}).json()
        tools = client.app.state.service_registry.resolve(ToolRuntimeManager)
        from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
        from dataclasses import replace

        registry = client.app.state.service_registry.resolve(ToolRegistry)
        original = registry.unregister("simulated_action")
        client.portal.call(tools.register, replace(original, definition=replace(original.definition, enabled=False)))

        client.post(f"/api/approvals/{body['approval_id']}/approve", headers=CONSOLE)
        done = wait(client, f"/api/executions/{body['execution_id']}", "completed", "failed")

        assert done["status"] == "completed" and "unavailable" in done["result"]["output"]
        assert approval(client, body["approval_id"])["state"] == "cancelled" and runs_of(client) == []


def test_a_decision_recorded_while_genesis_was_stopped_is_acted_on_once() -> None:
    import asyncio

    from backend.app.core.approval_gateway.application.approval_service import ApprovalService
    from backend.app.core.approval_gateway.domain.approval import DecisionSource
    from backend.app.core.approval_gateway.infrastructure.sqlalchemy_repository import SqlAlchemyApprovalRepository
    from backend.app.core.core_services.config.settings import settings
    from backend.app.core.core_services.event_bus import EventBus
    from backend.app.database import create_database_engine, create_session_factory

    with TestClient(app) as client:
        agent_id = agent(client, ActionProvider())
        body = client.post(f"/api/agents/{agent_id}/chat", json={"message": "Do it."}).json()

    async def approve_offline() -> None:
        engine = create_database_engine(settings.DATABASE_URL)
        try:
            service = ApprovalService(SqlAlchemyApprovalRepository(create_session_factory(engine)), EventBus())
            await service.approve(__import__("uuid").UUID(body["approval_id"]), source=DecisionSource.LOCAL_API)
        finally:
            await engine.dispose()

    asyncio.run(approve_offline())

    with TestClient(app) as restarted:
        restarted.app.state.service_registry.resolve(LLMProviderRegistry).register(ActionProvider())
        done = wait(restarted, f"/api/executions/{body['execution_id']}", "completed", "failed")
        assert done["status"] == "completed" and len(runs_of(restarted)) == 1
        assert approval(restarted, body["approval_id"])["state"] == "consumed"


# ------------------------------------------------------------------ size limits


def test_oversized_payloads_are_refused_before_anything_is_stored_or_run() -> None:
    with TestClient(app) as client:
        agent_id = agent(client, ActionProvider(), tools=["simulated_action", "echo"])
        huge_note = {"note": "n" * 20_000}

        operator = client.post("/api/tools/execute", json={"tool_name": "simulated_action", "arguments": huge_note}, headers=CONSOLE)
        metadata = client.post("/api/tools/execute", json={"tool_name": "echo", "arguments": {"message": "hi"}, "metadata": {"blob": ["m" * 5_000] * 4}}, headers=CONSOLE)
        execution = client.post(f"/api/agents/{agent_id}/execute", json={"metadata": {"tool_name": "echo", "tool_arguments": {"message": "e" * 9_000, "extra": "e" * 9_000}}})
        definition = client.post(
            "/api/workflow-definitions",
            json={"name": "big", "tasks": [{"task_id": "a", "name": "a", "tool_name": "simulated_action", "tool_arguments": huge_note}]},
        )

        assert operator.status_code == 422 and operator.json()["reason"] == "arguments_too_large"
        assert metadata.status_code == 422 and "16 KiB" in metadata.json()["detail"]
        assert execution.status_code == 422 and "16 KiB" in execution.json()["detail"]
        assert definition.status_code == 422 and "16,384" in definition.text
        assert "nnnn" not in operator.text + definition.text
        assert client.get("/api/approvals").json()["approvals"] == []
        assert client.get(f"/api/agents/{agent_id}/executions").json()["executions"] == []
        assert client.get("/api/workflow-definitions").json()["definitions"] == []
        assert client.get("/api/tools/history").json()["tasks"] == []
        # Normal-sized calls still work.
        assert client.post("/api/tools/execute", json={"tool_name": "echo", "arguments": {"message": "hi"}}, headers=CONSOLE).status_code == 200
