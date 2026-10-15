"""The local API answers only loopback hosts and refuses cross-site state changes (H2, M2).

These run against the real application. The test client's own host ("testserver") is
trusted by conftest; tests that need real behavior send explicit Host headers.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.core.api.local_request_guard import host_name
from backend.app.main import app


LOCAL = {"Host": "127.0.0.1:8000"}
FRONTEND = {**LOCAL, "Origin": "http://localhost:3000"}
EVIL = {**LOCAL, "Origin": "https://evil.example"}


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def idle_agent(client: TestClient, initialize: bool = True) -> str:
    response = client.post("/api/agents", json={"name": "a", "description": "d", "type": "t", "initialize": initialize}, headers=FRONTEND)
    assert response.status_code == 201
    return response.json()["id"]


def queued_run(client: TestClient) -> str:
    definition = client.post(
        "/api/workflow-definitions",
        json={"name": "w", "tasks": [{"task_id": "a", "name": "a", "tool_name": "delay", "tool_arguments": {"seconds": 0}}]},
        headers=FRONTEND,
    ).json()
    return client.post(f"/api/workflow-definitions/{definition['definition_id']}/runs", json={}, headers=FRONTEND).json()["workflow_id"]


# ----------------------------------------------------------------------- Host


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("localhost", "localhost"), ("LOCALHOST:8000", "localhost"), ("127.0.0.1:8000", "127.0.0.1"),
        ("[::1]", "::1"), ("[::1]:8000", "::1"), ("[::1]:x", None), ("[::1", None), ("localhost:", None),
        ("localhost:80:80", None), ("", None), (None, None), ("::1", None),
    ],
)
def test_host_header_parsing(header: str | None, expected: str | None) -> None:
    assert host_name(header) == expected


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000", "localhost"])
def test_loopback_hosts_are_served(client: TestClient, host: str) -> None:
    assert client.get("/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["attacker.example", "attacker.example:8000", "192.168.1.5:8000", "localhost.evil.com", "0.0.0.0:8000"])
def test_untrusted_hosts_are_refused_before_any_route_runs(client: TestClient, host: str) -> None:
    rebinding = client.get("/api/tools", headers={"Host": host})
    write = client.post("/api/tools/execute", json={"tool_name": "echo", "arguments": {"message": "x"}}, headers={"Host": host, "Origin": f"http://{host}"})

    assert rebinding.status_code == 400 and rebinding.json() == {"detail": "Untrusted Host header."}
    assert write.status_code == 400
    assert client.get("/api/tools/history").json()["tasks"] == []


# --------------------------------------------------------------------- Origin


def test_cross_site_requests_cannot_change_state(client: TestClient) -> None:
    agent_id = idle_agent(client)
    created = idle_agent(client, initialize=False)
    run_id = queued_run(client)

    attempts = {
        "stop Agent": client.post(f"/api/agents/{agent_id}/stop", headers=EVIL),
        "initialize Agent": client.post(f"/api/agents/{created}/initialize", headers=EVIL),
        "cancel workflow": client.post(f"/api/workflows/{run_id}/cancel", headers=EVIL),
        "delete Agent": client.delete(f"/api/agents/{agent_id}", headers=EVIL),
        "create Agent": client.post("/api/agents", json={"name": "x", "description": "d", "type": "t"}, headers=EVIL),
        "run tool": client.post("/api/tools/execute", json={"tool_name": "echo", "arguments": {"message": "x"}}, headers=EVIL),
        "queue tool work": client.post(f"/api/agents/{agent_id}/execute", json={"metadata": {"tool_name": "echo", "tool_arguments": {"message": "x"}}}, headers=EVIL),
        "null origin": client.post(f"/api/agents/{agent_id}/stop", headers={**LOCAL, "Origin": "null"}),
        "other loopback port": client.post(f"/api/agents/{agent_id}/stop", headers={**LOCAL, "Origin": "http://localhost:4000"}),
        "cross-site without Origin": client.post(f"/api/agents/{agent_id}/stop", headers={**LOCAL, "Sec-Fetch-Site": "cross-site"}),
    }

    assert {name: response.status_code for name, response in attempts.items()} == {name: 403 for name in attempts}
    assert client.get(f"/api/agents/{agent_id}").json()["status"] == "idle"
    assert client.get(f"/api/agents/{created}").json()["status"] == "created"
    assert client.get(f"/api/workflows/{run_id}").json()["status"] != "cancelled"
    assert len(client.get("/api/agents").json()["agents"]) == 2
    assert client.get("/api/tools/history").json()["tasks"] == []
    assert client.get("/api/executions").json()["executions"] == []


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001", "http://127.0.0.1:8000"],
)
def test_the_local_frontend_and_the_backends_own_pages_can_change_state(client: TestClient, origin: str) -> None:
    agent_id = idle_agent(client)
    headers = {**LOCAL, "Origin": origin}

    tool = client.post("/api/tools/execute", json={"tool_name": "calculator", "arguments": {"expression": "6 * 7"}}, headers=headers)
    stopped = client.post(f"/api/agents/{agent_id}/stop", headers=headers)

    assert tool.status_code == 200 and tool.json()["result"]["output"] == 42
    assert stopped.status_code == 200 and stopped.json()["status"] == "stopped"


def test_non_browser_clients_without_origin_still_work(client: TestClient) -> None:
    agent_id = idle_agent(client)

    assert client.post(f"/api/agents/{agent_id}/stop", headers=LOCAL).status_code == 200
    assert client.post("/api/tools/execute", json={"tool_name": "uuid", "arguments": {}}, headers={**LOCAL, "Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_reads_and_preflights_are_not_blocked_by_origin(client: TestClient) -> None:
    read = client.get("/api/tools", headers=EVIL)
    preflight = client.options(
        "/api/tools/execute",
        headers={**FRONTEND, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )

    assert read.status_code == 200 and "access-control-allow-origin" not in read.headers  # CORS: unreadable cross-site
    assert preflight.status_code == 200 and preflight.headers["access-control-allow-origin"] == "http://localhost:3000"


# ------------------------------------------------------------------ WebSocket


def test_event_stream_accepts_the_local_frontend(client: TestClient) -> None:
    with client.websocket_connect("/ws/events", headers=FRONTEND) as websocket:
        assert websocket.receive_json()["type"] == "connected"


@pytest.mark.parametrize("headers", [EVIL, {"Host": "attacker.example", "Origin": "http://attacker.example"}])
def test_event_stream_refuses_other_sites(client: TestClient, headers: dict) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/events", headers=headers) as websocket:
            websocket.receive_json()
