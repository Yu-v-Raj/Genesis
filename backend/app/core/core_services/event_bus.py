"""In-process typed event dispatch for Genesis Core services."""

from collections.abc import Awaitable, Callable, Mapping
from inspect import isawaitable
from threading import RLock
from typing import TypeAlias

from backend.app.core.observability.domain.events import Event


EventHandler: TypeAlias = Callable[[Event], Awaitable[None] | None]
EventSelector: TypeAlias = str | None


class EventBusError(Exception):
    """Base exception for Event Bus validation failures."""


class InvalidEventNameError(EventBusError):
    """Raised when an event type is empty or not a string."""


class InvalidEventHandlerError(EventBusError):
    """Raised when an event handler is not callable."""


class EventBus:
    """Publish typed events to synchronous or asynchronous subscribers."""

    def __init__(self) -> None:
        self._subscribers: dict[EventSelector, list[EventHandler]] = {}
        self._lock = RLock()

    def subscribe(
        self,
        event_type: str | EventHandler,
        handler: EventHandler | None = None,
    ) -> bool:
        """Subscribe a handler to an event type, or to all events when passed alone."""
        selector, resolved_handler = self._resolve_subscription(event_type, handler)
        with self._lock:
            handlers = self._subscribers.setdefault(selector, [])
            if resolved_handler in handlers:
                return False
            handlers.append(resolved_handler)
            return True

    def unsubscribe(
        self,
        event_type: str | EventHandler,
        handler: EventHandler | None = None,
    ) -> bool:
        """Remove a typed or all-event subscription if it exists."""
        selector, resolved_handler = self._resolve_subscription(event_type, handler)
        with self._lock:
            handlers = self._subscribers.get(selector)
            if handlers is None or resolved_handler not in handlers:
                return False
            handlers.remove(resolved_handler)
            if not handlers:
                del self._subscribers[selector]
            return True

    async def publish(
        self,
        event: Event | str,
        payload: Mapping[str, object] | None = None,
        *,
        source: str = "genesis",
    ) -> Event:
        """Dispatch an event and return the event envelope that was published.

        Passing a string remains supported for existing Core services. New callers
        should publish a typed ``Event`` subclass.
        """
        published_event = self._coerce_event(event, payload, source)
        with self._lock:
            handlers = tuple(self._subscribers.get(published_event.event_type, [])) + tuple(
                self._subscribers.get(None, [])
            )

        for handler in handlers:
            try:
                result = handler(published_event)
                if isawaitable(result):
                    await result
            except Exception:
                continue
        return published_event

    @staticmethod
    def _resolve_subscription(
        event_type: str | EventHandler,
        handler: EventHandler | None,
    ) -> tuple[EventSelector, EventHandler]:
        if handler is None:
            if not callable(event_type):
                raise InvalidEventHandlerError("Event handlers must be callable.")
            return None, event_type
        EventBus._validate_event_type(event_type)
        if not callable(handler):
            raise InvalidEventHandlerError("Event handlers must be callable.")
        return event_type, handler

    @staticmethod
    def _coerce_event(
        event: Event | str,
        payload: Mapping[str, object] | None,
        source: str,
    ) -> Event:
        if isinstance(event, Event):
            return event
        EventBus._validate_event_type(event)
        if not isinstance(source, str) or not source.strip():
            raise InvalidEventNameError("Event sources must be non-empty strings.")
        return Event(event_type=event, source=source, payload={} if payload is None else payload)

    @staticmethod
    def _validate_event_type(event_type: object) -> None:
        if not isinstance(event_type, str) or not event_type.strip():
            raise InvalidEventNameError("Event types must be non-empty strings.")
