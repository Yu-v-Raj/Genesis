"""Unit tests for Genesis observability services."""

import asyncio

import pytest

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.application.heartbeat import HeartbeatService
from backend.app.core.observability.application.logger_service import LoggerService
from backend.app.core.observability.domain.events import Event, Heartbeat, LogCreated, SystemStarted
from backend.app.core.observability.infrastructure.event_history import EventHistory


@pytest.mark.asyncio
async def test_typed_event_is_dispatched_to_sync_and_async_handlers() -> None:
    """The bus supports typed events and both handler styles."""
    bus = EventBus()
    received: list[Event] = []

    def sync_handler(event: Event) -> None:
        received.append(event)

    async def async_handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("system.started", sync_handler)
    bus.subscribe(async_handler)

    event = SystemStarted(source="test", payload={"component": "runtime"})
    assert await bus.publish(event) is event
    assert received == [event, event]
    assert event.id
    assert event.timestamp.tzinfo is not None
    assert event.event_type == "system.started"


def test_event_history_overwrites_oldest_event_at_capacity() -> None:
    """History retains only its configured number of newest events."""
    history = EventHistory(capacity=2)
    first = Event(event_type="first")
    second = Event(event_type="second")
    third = Event(event_type="third")

    history.record(first)
    history.record(second)
    history.record(third)

    assert history.recent() == (third, second)
    assert history.latest() is third
    assert history.event_types() == ("second", "third")


@pytest.mark.asyncio
async def test_logger_writes_a_log_created_event() -> None:
    """LoggerService publishes structured log events after logging."""
    bus = EventBus()
    history = EventHistory()
    bus.subscribe(history.record)
    logger = LoggerService(bus)

    await logger.error("example failure", source="test", task_id="task-1")

    event = history.latest()
    assert isinstance(event, LogCreated)
    assert event.payload == {
        "level": "ERROR",
        "message": "example failure",
        "context": {"task_id": "task-1"},
    }


@pytest.mark.asyncio
async def test_heartbeat_contains_runtime_data() -> None:
    """Heartbeat events contain current uptime and runtime state."""
    bus = EventBus()
    history = EventHistory()
    bus.subscribe(history.record)
    heartbeat = HeartbeatService(
        bus,
        runtime_state=lambda: "running",
        uptime=lambda: 12.5,
        interval_seconds=1,
    )

    await heartbeat.publish_once()

    event = history.latest()
    assert isinstance(event, Heartbeat)
    assert event.payload == {"uptime": 12.5, "runtime_state": "running"}


@pytest.mark.asyncio
async def test_heartbeat_stops_its_background_task() -> None:
    """Stopping a heartbeat cancels its active background task."""
    heartbeat = HeartbeatService(
        EventBus(),
        runtime_state=lambda: "running",
        uptime=lambda: 0.0,
        interval_seconds=60,
    )

    await heartbeat.start()
    await asyncio.sleep(0)
    await heartbeat.stop()
