"""API tests for the read-only Genesis System API."""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide a client with the application lifespan active."""
    with TestClient(app) as test_client:
        yield test_client


def test_system_health_returns_live_process_data(client: TestClient) -> None:
    """Health reports runtime status, version, and non-negative uptime."""
    response = client.get("/api/system/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["version"] == "0.1.0"
    assert payload["uptime"] >= 0


def test_system_runtime_returns_current_state(client: TestClient) -> None:
    """Runtime state is exposed through the read-only API."""
    response = client.get("/api/system/runtime")

    assert response.status_code == 200
    assert response.json() == {"state": "running"}


def test_system_services_returns_registered_core_services(client: TestClient) -> None:
    """Services endpoint reflects the app-scoped service registry."""
    response = client.get("/api/system/services")

    assert response.status_code == 200
    assert response.json() == {
        "services": [
            "EventBus",
            "ToolManager",
            "PluginManager",
            "MemoryManager",
            "WorkflowEngine",
            "RuntimeLifecycleManager",
        ]
    }


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/system/tools", {"tools": []}),
        ("/api/system/plugins", {"plugins": []}),
        ("/api/system/memory", {"providers": []}),
        ("/api/system/workflows", {"workflows": []}),
    ],
)
def test_system_manager_endpoints_return_live_empty_registries(
    client: TestClient,
    path: str,
    expected: dict[str, list[str]],
) -> None:
    """Manager endpoints expose their current registrations without mutation."""
    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == expected
