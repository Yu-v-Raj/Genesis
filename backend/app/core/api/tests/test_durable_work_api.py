"""HTTP contract for v0.12 durable executions and workflows."""

import time
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app


def wait_for(client: TestClient, path: str, status: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        body = client.get(path).json()
        if body["status"] == status:
            return body
        assert time.monotonic() < deadline, f"{path} stayed {body['status']}, expected {status}"
        time.sleep(0.02)


def ready_agent(client: TestClient) -> str:
    agent_id = client.post("/api/agents", json={"name": "worker", "description": "d", "type": "t", "initialize": True}).json()["id"]
    return agent_id


def calculator_flow(expression: str = "6 * 7") -> dict:
    return {
        "name": "Compute and echo",
        "tasks": [
            {"task_id": "compute", "name": "Compute", "tool_name": "calculator", "tool_arguments": {"expression": expression}},
            {"task_id": "report", "name": "Report", "tool_name": "echo", "tool_arguments": {"message": "done"}, "dependencies": ["compute"]},
        ],
    }


def test_tool_execution_is_durable_inspectable_and_safe_to_expose() -> None:
    with TestClient(app) as client:
        agent_id = ready_agent(client)
        queued = client.post(
            f"/api/agents/{agent_id}/execute",
            json={"metadata": {"tool_name": "calculator", "tool_arguments": {"expression": "6 * 7"}}},
        )
        assert queued.status_code == 202
        execution_id = queued.json()["execution_id"]

        done = wait_for(client, f"/api/executions/{execution_id}", "completed")
        assert done["result"]["output"] == "42"
        assert done["attempt"] == 1 and done["retry"]["allowed"] is False
        assert "lease_owner" not in done and "version" not in done

        history = client.get(f"/api/executions/{execution_id}/history").json()["transitions"]
        assert [step["to_status"] for step in history] == ["pending", "queued", "starting", "running", "completed"]
        assert client.get(f"/api/executions/{uuid4()}/history").status_code == 404

    with TestClient(app) as restarted:
        survived = restarted.get(f"/api/executions/{execution_id}").json()
        assert survived["status"] == "completed"
        assert restarted.get("/api/executions").json()["executions"][0]["execution_id"] == execution_id


def test_failed_and_cancelled_work_can_be_retried_but_finished_work_cannot() -> None:
    with TestClient(app) as client:
        agent_id = ready_agent(client)
        failing = client.post(f"/api/agents/{agent_id}/execute", json={"metadata": {"tool_name": "not_a_tool"}}).json()
        failed = wait_for(client, f"/api/executions/{failing['execution_id']}", "failed")
        assert failed["error_category"] == "tool_failed"
        assert failed["retry"] == {"allowed": True, "requires_acknowledgement": False, "reason": "Retrying starts a new attempt with the same input."}

        retried = client.post(f"/api/executions/{failing['execution_id']}/retry", json={})
        assert retried.status_code == 202
        assert (retried.json()["attempt"], retried.json()["retry_of"]) == (2, failing["execution_id"])

        ok = client.post(f"/api/agents/{agent_id}/execute", json={"metadata": {"tool_name": "echo", "tool_arguments": {"message": "hi"}}}).json()
        wait_for(client, f"/api/executions/{ok['execution_id']}", "completed")
        refused = client.post(f"/api/executions/{ok['execution_id']}/retry", json={})
        assert refused.status_code == 409
        assert "cannot be retried" in refused.json()["detail"]


def test_workflow_definitions_are_versioned_and_runs_snapshot_them() -> None:
    with TestClient(app) as client:
        assert client.post("/api/workflow-definitions", json={**calculator_flow(), "tasks": [{"task_id": "x", "name": "x", "tool_name": "rm_rf"}]}).status_code == 422

        created = client.post("/api/workflow-definitions", json=calculator_flow("1 + 1"))
        assert created.status_code == 201
        definition_id = created.json()["definition_id"]
        updated = client.put(f"/api/workflow-definitions/{definition_id}", json=calculator_flow("6 * 7"))
        assert updated.json()["version"] == 2
        assert client.get(f"/api/workflow-definitions/{definition_id}", params={"version": 1}).json()["tasks"][0]["configuration"]["tool_arguments"] == {"expression": "1 + 1"}
        assert [d["version"] for d in client.get("/api/workflow-definitions").json()["definitions"]] == [2]

        run = client.post(f"/api/workflow-definitions/{definition_id}/runs", json={})
        assert run.status_code == 201 and run.json()["definition_version"] == 2
        done = wait_for(client, f"/api/workflows/{run.json()['workflow_id']}", "completed")
        assert [t["result"] for t in done["tasks"]] == [42, "done"]
        assert done["retry"]["allowed"] is False
        assert client.post(f"/api/workflows/{done['workflow_id']}/retry", json={}).status_code == 409
        assert client.post(f"/api/workflow-definitions/{uuid4()}/runs", json={}).status_code == 404

    with TestClient(app) as restarted:
        assert restarted.get(f"/api/workflows/{done['workflow_id']}").json()["status"] == "completed"
        assert restarted.get(f"/api/workflow-definitions/{definition_id}").json()["version"] == 2


def test_original_workflow_contract_still_works() -> None:
    with TestClient(app) as client:
        created = client.post("/api/workflows", json=calculator_flow())
        assert created.status_code == 201
        body = created.json()
        assert body["status"] == "created" and body["definition_version"] == 1
        workflow_id = body["workflow_id"]
        assert client.post(f"/api/workflows/{workflow_id}/start").json()["status"] in {"queued", "running", "completed"}
        wait_for(client, f"/api/workflows/{workflow_id}", "completed")
        assert len(client.get(f"/api/workflows/{workflow_id}/tasks").json()["tasks"]) == 2
        assert client.post(f"/api/workflows/{workflow_id}/pause").status_code == 409
        assert client.post(f"/api/workflows/{workflow_id}/explode").status_code == 404
        assert client.delete(f"/api/workflows/{workflow_id}").status_code == 200
