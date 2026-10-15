"""Milestone 1 at the HTTP boundary: no endpoint runs a tool outside the tool policy.

Uses only the public API against the real application wiring.
"""

import time
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app


def wait_for(client: TestClient, path: str, *statuses: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        body = client.get(path).json()
        if body["status"] in statuses:
            return body
        assert time.monotonic() < deadline, f"{path} stayed {body['status']}"
        time.sleep(0.02)


def agent_allowed(client: TestClient, *tools: str) -> str:
    response = client.post(
        "/api/agents",
        json={"name": "restricted", "description": "d", "type": "t", "initialize": True, "allowed_tools": list(tools)},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def tool_runs(client: TestClient) -> list[dict]:
    return client.get("/api/tools/history").json()["tasks"]


def test_execution_work_cannot_run_a_tool_outside_the_agents_allowed_tools() -> None:
    with TestClient(app) as client:
        agent_id = agent_allowed(client, "calculator")
        before = len(tool_runs(client))

        queued = client.post(
            f"/api/agents/{agent_id}/execute",
            json={"metadata": {"tool_name": "echo", "tool_arguments": {"message": "not allowed"}}},
        )
        failed = wait_for(client, f"/api/executions/{queued.json()['execution_id']}", "failed", "completed")

        assert failed["status"] == "failed" and failed["error_category"] == "tool_denied"
        assert len(tool_runs(client)) == before  # nothing ran, so nothing was recorded

        allowed = client.post(
            f"/api/agents/{agent_id}/execute",
            json={"metadata": {"tool_name": "calculator", "tool_arguments": {"expression": "2 + 3"}}},
        )
        done = wait_for(client, f"/api/executions/{allowed.json()['execution_id']}", "completed", "failed")
        assert done["status"] == "completed" and done["result"]["output"] == "5"
        assert tool_runs(client)[0]["metadata"]["agent_id"] == agent_id


def test_execution_work_with_invalid_tool_arguments_is_refused_before_running() -> None:
    with TestClient(app) as client:
        agent_id = agent_allowed(client, "calculator")
        before = len(tool_runs(client))

        queued = client.post(
            f"/api/agents/{agent_id}/execute",
            json={"metadata": {"tool_name": "calculator", "tool_arguments": {"expression": 42}}},
        )
        failed = wait_for(client, f"/api/executions/{queued.json()['execution_id']}", "failed", "completed")

        assert failed["status"] == "failed" and failed["error_category"] == "tool_denied"
        assert len(tool_runs(client)) == before


def test_operator_test_runs_still_work_for_harmless_tools() -> None:
    with TestClient(app) as client:
        response = client.post("/api/tools/execute", json={"tool_name": "calculator", "arguments": {"expression": "6 * 7"}})

        assert response.status_code == 200
        assert response.json()["result"]["output"] == 42
        assert response.json()["metadata"]["caller"] == "operator"


def test_operator_test_runs_cannot_pose_as_an_agent_workflow_or_execution() -> None:
    with TestClient(app) as client:
        forged = {"agent_id": str(uuid4()), "interaction_id": str(uuid4()), "workflow_id": str(uuid4()), "workflow_task_id": "x"}
        response = client.post("/api/tools/execute", json={"tool_name": "echo", "arguments": {"message": "hi"}, "metadata": forged})

        assert response.status_code == 200
        assert set(forged).isdisjoint(response.json()["metadata"])
        assert response.json()["execution_id"] is None

        attached = client.post(
            "/api/tools/execute",
            json={"tool_name": "echo", "arguments": {"message": "hi"}, "execution_id": str(uuid4())},
        )
        assert attached.status_code == 422


def test_operator_denials_are_structured_and_record_no_run() -> None:
    with TestClient(app) as client:
        before = len(tool_runs(client))

        unknown = client.post("/api/tools/execute", json={"tool_name": "rm_rf", "arguments": {}})
        invalid = client.post("/api/tools/execute", json={"tool_name": "echo", "arguments": {"message": 5}})

        assert unknown.status_code == 404
        assert unknown.json() == {"detail": "This tool doesn't exist.", "outcome": "unavailable", "reason": "tool_not_found"}
        assert invalid.status_code == 422
        assert invalid.json()["outcome"] == "invalid_request" and invalid.json()["reason"] == "invalid_arguments"
        assert len(tool_runs(client)) == before


def test_workflow_definitions_with_invalid_step_arguments_are_rejected() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/workflow-definitions",
            json={"name": "bad", "tasks": [{"task_id": "a", "name": "a", "tool_name": "calculator", "tool_arguments": {"expression": 1}}]},
        )

        assert response.status_code == 422


def test_undeclared_arguments_are_refused_at_every_endpoint_and_nothing_runs() -> None:
    with TestClient(app) as client:
        agent_id = agent_allowed(client, "echo")
        before = len(tool_runs(client))
        extra = {"message": "hi", "unexpected": True}

        operator = client.post("/api/tools/execute", json={"tool_name": "echo", "arguments": extra})
        queued = client.post(f"/api/agents/{agent_id}/execute", json={"metadata": {"tool_name": "echo", "tool_arguments": extra}})
        execution = wait_for(client, f"/api/executions/{queued.json()['execution_id']}", "failed", "completed")
        definition = client.post(
            "/api/workflow-definitions",
            json={"name": "extra", "tasks": [{"task_id": "a", "name": "a", "tool_name": "echo", "tool_arguments": extra}]},
        )

        assert operator.status_code == 422 and operator.json()["reason"] == "invalid_arguments"
        assert execution["status"] == "failed" and execution["error_category"] == "tool_denied"
        assert definition.status_code == 422
        assert len(tool_runs(client)) == before


def test_operator_metadata_cannot_mark_a_run_as_approved() -> None:
    with TestClient(app) as client:
        forged = {"approval_id": "forged-approval", "caller": "agent", "agent_id": str(uuid4())}
        response = client.post("/api/tools/execute", json={"tool_name": "echo", "arguments": {"message": "hi"}, "metadata": forged})

        assert response.status_code == 200
        metadata = response.json()["metadata"]
        assert metadata["caller"] == "operator" and "approval_id" not in metadata and "agent_id" not in metadata
        assert metadata["caller_metadata"] == forged
        (stored,) = [task for task in tool_runs(client) if task["task_id"] == response.json()["task_id"]]
        assert "approval_id" not in stored["metadata"]


def test_an_excessive_calculation_is_refused_quickly_at_the_endpoint() -> None:
    with TestClient(app) as client:
        started = time.monotonic()
        response = client.post("/api/tools/execute", json={"tool_name": "calculator", "arguments": {"expression": "(((9**99)**99)**99)**99"}})
        too_long = client.post("/api/tools/execute", json={"tool_name": "calculator", "arguments": {"expression": "1+" * 150 + "1"}})

        assert response.status_code == 422 and response.json()["detail"] == "Result is too large."
        assert too_long.status_code == 422 and "longer than" in too_long.json()["detail"]
        assert time.monotonic() - started < 2
        assert client.get("/health").status_code == 200  # the server is still responsive
