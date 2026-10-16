"""Milestone 3 end to end: one request or workflow run can be followed through every
runtime, the history survives a restart, and reading it never changes anything.

Real application wiring and a freshly migrated database per test. The only "side effect"
is ``simulated_action``, which does nothing outside Genesis.
"""

import json
import time
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, ToolCall
from backend.app.core.observability.application.durable_event_recorder import DurableEventRecorder
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.domain.task import Task
from backend.app.main import app


CONSOLE = {"Origin": "http://localhost:3000"}
SECRET_MESSAGE = "Please do it, the code word is marmalade."


class ActionProvider(LLMProvider):
    """Asks for ``simulated_action`` once, then answers with what the tool said."""

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider="fake", model_name="fake-1", metadata={"configured": True}),)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if request.messages[-1].role.value == "tool":
            return LLMResponse(content="Done.", model=request.model)
        return LLMResponse(content=None, model=request.model, tool_calls=(ToolCall(call_id="call-0", name="simulated_action", arguments={"note": "hello"}),))


def wait(client: TestClient, path: str, *statuses: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while (body := client.get(path).json())["status"] not in statuses:
        assert time.monotonic() < deadline, f"{path} stayed {body['status']}"
        time.sleep(0.02)
    return body


def flush(client: TestClient) -> None:
    """Write events the background recorder hasn't stored yet (it batches every 0.5 s)."""
    recorder = client.app.state.service_registry.resolve(DurableEventRecorder)
    assert client.portal.call(recorder.flush)


def approved_chat(client: TestClient) -> tuple[str, str]:
    client.app.state.service_registry.resolve(LLMProviderRegistry).register(ActionProvider())
    agent = client.post(
        "/api/agents",
        json={"name": "Courier", "description": "d", "type": "assistant", "llm_model": {"provider": "fake", "model_name": "fake-1"},
              "allowed_tools": ["simulated_action"], "initialize": True},
    )
    assert agent.status_code == 201, agent.text
    held = client.post(f"/api/agents/{agent.json()['id']}/chat", json={"message": SECRET_MESSAGE}).json()
    assert held["status"] == "waiting_approval"
    assert client.post(f"/api/approvals/{held['approval_id']}/approve", headers=CONSOLE).status_code == 200
    wait(client, f"/api/executions/{held['execution_id']}", "completed")
    return held["execution_id"], held["approval_id"]


def approved_workflow(client: TestClient) -> str:
    definition = client.post(
        "/api/workflow-definitions",
        json={"name": "Notify", "tasks": [
            {"task_id": "send", "name": "Send", "tool_name": "simulated_action", "tool_arguments": {"note": "deploy done"}},
            {"task_id": "after", "name": "After", "tool_name": "echo", "tool_arguments": {"message": "sent"}, "dependencies": ["send"]},
        ]},
    ).json()
    run = client.post(f"/api/workflow-definitions/{definition['definition_id']}/runs", json={"start": True}).json()
    waiting = wait(client, f"/api/workflows/{run['workflow_id']}", "waiting_approval")
    approval_id = next(task["approval_id"] for task in waiting["tasks"] if task["task_id"] == "send")
    assert client.post(f"/api/approvals/{approval_id}/approve", headers=CONSOLE).status_code == 200
    wait(client, f"/api/workflows/{run['workflow_id']}", "completed")
    return run["workflow_id"]


def test_an_agent_request_is_traceable_from_execution_to_model_calls_tools_and_approvals() -> None:
    with TestClient(app) as client:
        execution_id, approval_id = approved_chat(client)
        flush(client)
        trace = client.get(f"/api/operations/executions/{execution_id}/trace")
        assert trace.status_code == 200, trace.text
        body = trace.json()

        assert body["execution"]["status"] == "completed"
        statuses = [t["to_status"] for t in body["transitions"]]
        assert "waiting_approval" in statuses and statuses[-1] == "completed"
        assert [(call["provider"], call["model"], call["outcome"], call["attempts"]) for call in body["model_calls"]] == [("fake", "fake-1", "completed", 1)] * 2
        (task,) = body["tool_tasks"]
        assert task["tool_name"] == "simulated_action" and task["status"] == "completed" and task["execution_id"] == execution_id
        assert task["metadata"]["approval_id"] == approval_id and task["arguments"] == {"note": "hello"}
        (approval,) = body["approvals"]
        assert (approval["approval_id"], approval["state"], approval["outcome"], approval["task_id"]) == (approval_id, "consumed", "completed", task["task_id"])

        types = [event["event_type"] for event in body["events"]]
        for expected in ("execution.created", "execution.waiting_approval", "approval.requested", "approval.approved", "task.created", "task.completed", "llm.completed", "execution.completed"):
            assert expected in types, expected
        sequences = [event["sequence"] for event in body["events"]]
        assert sequences == sorted(sequences)  # oldest first
        assert all(execution_id in (event["execution_id"], event["interaction_id"]) for event in body["events"])
        tool_events = [event for event in body["events"] if event["event_type"].startswith("task.")]
        assert {event["tool_task_id"] for event in tool_events} == {task["task_id"]}
        assert body["truncated"] == {"tool_tasks": False, "approvals": False, "events": False}
        # Events, model calls and tool runs never carry message content (the execution record
        # itself holds the request, exactly as GET /api/executions/{id} always has).
        assert "marmalade" not in json.dumps([body["events"], body["model_calls"], body["tool_tasks"]])

        assert client.get("/api/operations/executions/00000000-0000-0000-0000-000000000000/trace").status_code == 404


def test_a_workflow_run_is_traceable_through_its_steps_tool_tasks_and_approvals() -> None:
    with TestClient(app) as client:
        run_id = approved_workflow(client)
        flush(client)
        body = client.get(f"/api/operations/workflows/{run_id}/trace").json()

        assert body["run"]["status"] == "completed"
        send = [(t["from_status"], t["to_status"]) for t in body["transitions"] if t["step_id"] == "send"]
        assert send == [("pending", "ready"), ("ready", "running"), ("running", "waiting_approval"), ("waiting_approval", "pending"),
                        ("pending", "ready"), ("ready", "running"), ("running", "completed")]
        run_changes = [t["to_status"] for t in body["transitions"] if t["step_id"] is None]
        assert run_changes == ["created", "queued", "running", "waiting_approval", "queued", "running", "completed"]
        assert {t["worker"] for t in body["transitions"] if t["to_status"] == "running" and t["step_id"] is None} != {None}

        by_tool = {task["tool_name"]: task for task in body["tool_tasks"]}
        assert set(by_tool) == {"simulated_action", "echo"}
        assert by_tool["simulated_action"]["metadata"]["workflow_task_id"] == "send"
        assert by_tool["echo"]["metadata"]["workflow_task_id"] == "after"
        (approval,) = body["approvals"]
        assert approval["subject"]["step_id"] == "send" and approval["task_id"] == by_tool["simulated_action"]["task_id"]

        step_events = {(e["event_type"], e["step_id"]) for e in body["events"] if e["event_type"].startswith("workflow.task.")}
        assert ("workflow.task.waiting_approval", "send") in step_events and ("workflow.task.completed", "after") in step_events
        assert all(e["tool_task_id"] is None for e in body["events"] if e["event_type"].startswith("workflow."))
        assert client.get("/api/operations/workflows/00000000-0000-0000-0000-000000000000/trace").status_code == 404


def test_history_survives_a_restart() -> None:
    with TestClient(app) as client:
        execution_id, _ = approved_chat(client)
        run_id = approved_workflow(client)
        before = client.get("/api/tools/history").json()["tasks"]
    # The application shut down (its recorder wrote what was pending); start it again.
    with TestClient(app) as client:
        after = client.get("/api/tools/history").json()["tasks"]
        assert [t["task_id"] for t in after] == [t["task_id"] for t in before] and len(after) == 3
        trace = client.get(f"/api/operations/executions/{execution_id}/trace").json()
        assert len(trace["tool_tasks"]) == 1 and len(trace["model_calls"]) == 2 and trace["events"]
        run = client.get(f"/api/operations/workflows/{run_id}/trace").json()
        assert run["transitions"][-1]["to_status"] == "completed" and len(run["tool_tasks"]) == 2


def test_lists_page_with_cursors_and_filters() -> None:
    with TestClient(app) as client:
        for message in ("one", "two", "three"):
            assert client.post("/api/tools/execute", json={"tool_name": "echo", "arguments": {"message": message}}).status_code == 200
        first = client.get("/api/tools/history", params={"limit": 2}).json()
        rest = client.get("/api/tools/history", params={"limit": 2, "before": first["next_before"]}).json()
        assert [t["result"]["output"] for t in first["tasks"] + rest["tasks"]] == ["three", "two", "one"]
        assert first["next_before"] is not None and rest["next_before"] is None
        assert client.get("/api/tools/history", params={"tool_name": "uuid"}).json()["tasks"] == []

        flush(client)
        page = client.get("/api/operations/events", params={"limit": 2, "event_type": "task."}).json()
        older = client.get("/api/operations/events", params={"limit": 50, "event_type": "task.", "before_sequence": page["next_before_sequence"]}).json()
        everything = page["events"] + older["events"]
        assert len(everything) == 6 and all(e["event_type"].startswith("task.") for e in everything)  # created + completed, x3
        assert [e["sequence"] for e in everything] == sorted((e["sequence"] for e in everything), reverse=True)
        assert older["next_before_sequence"] is None
        assert client.get("/api/operations/events", params={"limit": 0}).status_code == 422
        assert client.get("/api/operations/events", params={"limit": 501}).status_code == 422
        assert all(e["event_type"] != "log.created" for e in client.get("/api/operations/events", params={"limit": 500}).json()["events"])

        for _ in range(3):
            assert client.post("/api/workflows", json={"name": "W", "tasks": [{"task_id": "a", "name": "A", "tool_name": "echo", "tool_arguments": {"message": "m"}}]}).status_code == 201
        runs = client.get("/api/workflows", params={"limit": 2}).json()
        older_runs = client.get("/api/workflows", params={"limit": 2, "before": runs["next_before"]}).json()
        assert len(runs["workflows"]) == 2 and len(older_runs["workflows"]) == 1 and older_runs["next_before"] is None
        assert client.get("/api/executions", params={"limit": 1}).json()["next_before"] is None  # no executions yet


def test_cursors_never_skip_runs_that_share_a_timestamp() -> None:
    with TestClient(app) as client:
        store = client.app.state.service_registry.resolve(ToolRuntimeManager)._task_store
        moment = datetime(2026, 10, 16, 10, 0, 0, 500000, tzinfo=UTC)
        tied = [Task(execution_id=None, tool_name="echo", created_at=moment) for _ in range(7)]
        for task in tied:
            client.portal.call(store.save, task)

        seen: list[str] = []
        cursor = None
        while True:
            body = client.get("/api/tools/history", params={"limit": 2, **({"before": cursor} if cursor else {})}).json()
            seen.extend(task["task_id"] for task in body["tasks"])
            cursor = body["next_before"]
            if cursor is None:
                break
        assert len(seen) == len(set(seen)) == 7
        assert set(seen) == {str(task.task_id) for task in tied}

        assert client.get("/api/tools/history", params={"before": "not-a-cursor"}).status_code == 422
        assert client.get("/api/executions", params={"before": "2026-10-16T10:00:00Z_zz"}).status_code == 422
        # A bare time still works and means "created strictly before it".
        assert client.get("/api/tools/history", params={"before": "2026-10-16T10:00:00.500000+00:00"}).json()["tasks"] == []
        assert len(client.get("/api/tools/history", params={"before": "2026-10-16T10:00:01Z"}).json()["tasks"]) == 7


def test_reading_traces_and_history_changes_nothing() -> None:
    with TestClient(app) as client:
        client.app.state.service_registry.resolve(LLMProviderRegistry).register(ActionProvider())
        agent = client.post(
            "/api/agents",
            json={"name": "Courier", "description": "d", "type": "assistant", "llm_model": {"provider": "fake", "model_name": "fake-1"},
                  "allowed_tools": ["simulated_action"], "initialize": True},
        ).json()
        held = client.post(f"/api/agents/{agent['id']}/chat", json={"message": "hold"}).json()
        flush(client)
        execution_before = client.get(f"/api/executions/{held['execution_id']}").json()
        approval_before = client.get(f"/api/approvals/{held['approval_id']}").json()
        events_before = client.get("/api/operations/events", params={"limit": 500}).json()

        for _ in range(3):
            assert client.get(f"/api/operations/executions/{held['execution_id']}/trace").status_code == 200
            assert client.get("/api/operations/events", params={"execution_id": held["execution_id"]}).status_code == 200
            assert client.get("/api/tools/history").status_code == 200
        flush(client)

        execution_after = client.get(f"/api/executions/{held['execution_id']}").json()
        # ``duration`` is computed from the clock at read time; everything stored is unchanged.
        assert {k: v for k, v in execution_after.items() if k != "duration"} == {k: v for k, v in execution_before.items() if k != "duration"}
        assert execution_after["status"] == "waiting_approval"
        assert client.get(f"/api/approvals/{held['approval_id']}").json() == approval_before
        assert client.get("/api/operations/events", params={"limit": 500}).json() == events_before
        assert json.dumps(events_before).count("pending") >= 1
