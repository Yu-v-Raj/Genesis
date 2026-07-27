"""Integration tests for the Genesis WebSocket event stream."""

import pytest
from fastapi.testclient import TestClient

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import SystemStarted
from backend.app.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide an application client with the lifespan active."""
    with TestClient(app) as test_client:
        yield test_client


def test_event_stream_acknowledges_and_forwards_events(client: TestClient) -> None:
    """A connected client receives Event Bus publications unchanged in meaning."""
    event_bus = client.app.state.service_registry.resolve(EventBus)

    with client.websocket_connect("/ws/events") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"
        assert "timestamp" in connected

        client.portal.call(event_bus.publish, SystemStarted(source="test", payload={"run": "one"}))
        message = websocket.receive_json()

    assert message == {
        "type": "event",
        "event": {
            "id": message["event"]["id"],
            "timestamp": message["event"]["timestamp"],
            "event_type": "system.started",
            "source": "test",
            "payload": {"run": "one"},
        },
    }
