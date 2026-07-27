"""API tests for Genesis observability endpoints."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.app.core.observability.application.logger_service import LoggerService
from backend.app.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide a client with the application lifespan active."""
    with TestClient(app) as test_client:
        yield test_client


def test_events_endpoints_return_live_event_history(client: TestClient) -> None:
    """Event endpoints expose the events created during application startup."""
    events_response = client.get("/api/events")
    latest_response = client.get("/api/events/latest")
    types_response = client.get("/api/events/types")

    assert events_response.status_code == 200
    events = events_response.json()["events"]
    assert events
    assert {"id", "timestamp", "event_type", "source", "payload"} == set(events[0])
    assert latest_response.json()["event"]["event_type"] == "log.created"
    assert "system.started" in types_response.json()["event_types"]


def test_log_endpoints_return_structured_log_events(client: TestClient) -> None:
    """Log endpoints expose startup logs and filter error logs."""
    logger = client.app.state.service_registry.resolve(LoggerService)
    asyncio.run(logger.error("observability test failure", source="test"))

    logs_response = client.get("/api/logs")
    errors_response = client.get("/api/logs/errors")

    assert logs_response.status_code == 200
    assert any(
        event["payload"]["message"] == "Genesis application startup"
        for event in logs_response.json()["events"]
    )
    assert errors_response.json()["events"][0]["payload"]["message"] == "observability test failure"
