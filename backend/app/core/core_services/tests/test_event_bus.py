"""Unit tests for the in-process Core Event Bus."""

import pytest

from backend.app.core.core_services.event_bus import Event, EventBus


@pytest.mark.asyncio
async def test_subscribed_handler_receives_published_event() -> None:
    """Subscribers receive an event's name and payload."""
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("runtime.started", handler)
    await bus.publish("runtime.started", {"runtime_id": "example"})

    assert len(received) == 1
    event = received[0]
    assert event.name == "runtime.started"
    assert event.payload == {"runtime_id": "example"}


@pytest.mark.asyncio
async def test_unsubscribed_handler_no_longer_receives_events() -> None:
    """Unsubscribing removes a handler from future dispatches."""
    bus = EventBus()
    received: list[str] = []

    async def handler(_: Event) -> None:
        received.append("called")

    assert bus.subscribe("runtime.started", handler)
    assert bus.unsubscribe("runtime.started", handler)
    await bus.publish("runtime.started")

    assert received == []


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_same_event() -> None:
    """Every subscribed handler is invoked for the same event."""
    bus = EventBus()
    received: list[str] = []

    async def first_handler(_: Event) -> None:
        received.append("first")

    async def second_handler(_: Event) -> None:
        received.append("second")

    bus.subscribe("runtime.started", first_handler)
    bus.subscribe("runtime.started", second_handler)

    await bus.publish("runtime.started")

    assert received == ["first", "second"]


@pytest.mark.asyncio
async def test_publish_without_subscribers_completes_successfully() -> None:
    """Publishing an event without subscribers is a no-op."""
    await EventBus().publish("runtime.started")


@pytest.mark.asyncio
async def test_subscriber_failure_does_not_block_other_subscribers() -> None:
    """A failing subscriber does not prevent subsequent delivery."""
    bus = EventBus()
    received: list[str] = []

    async def failing_handler(_: Event) -> None:
        raise RuntimeError("expected test failure")

    async def successful_handler(_: Event) -> None:
        received.append("delivered")

    bus.subscribe("runtime.started", failing_handler)
    bus.subscribe("runtime.started", successful_handler)

    await bus.publish("runtime.started")

    assert received == ["delivered"]


@pytest.mark.asyncio
async def test_duplicate_subscription_is_idempotent() -> None:
    """The same handler is invoked once even when subscribed repeatedly."""
    bus = EventBus()
    received: list[str] = []

    async def handler(_: Event) -> None:
        received.append("called")

    assert bus.subscribe("runtime.started", handler)
    assert not bus.subscribe("runtime.started", handler)
    await bus.publish("runtime.started")

    assert received == ["called"]
