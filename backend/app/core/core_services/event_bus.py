"""In-process asynchronous event dispatch for Genesis Core services."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from threading import RLock
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class Event:
    """A named event published by a Core service."""

    name: str
    payload: object | None = None


EventHandler: TypeAlias = Callable[[Event], Awaitable[None]]


class EventBusError(Exception):
    """Base exception for Event Bus validation failures."""


class InvalidEventNameError(EventBusError):
    """Raised when an event name is empty or not a string."""


class InvalidEventHandlerError(EventBusError):
    """Raised when an event handler is not callable."""


class EventBus:
    """Publish named events to subscribed asynchronous handlers."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._lock = RLock()

    def subscribe(self, event_name: str, handler: EventHandler) -> bool:
        """Subscribe a handler and return whether it was newly registered."""
        self._validate_event_name(event_name)
        if not callable(handler):
            raise InvalidEventHandlerError("Event handlers must be callable.")

        with self._lock:
            handlers = self._subscribers.setdefault(event_name, [])
            if handler in handlers:
                return False
            handlers.append(handler)
            return True

    def unsubscribe(self, event_name: str, handler: EventHandler) -> bool:
        """Remove a handler and return whether a subscription existed."""
        self._validate_event_name(event_name)
        if not callable(handler):
            raise InvalidEventHandlerError("Event handlers must be callable.")

        with self._lock:
            handlers = self._subscribers.get(event_name)
            if handlers is None or handler not in handlers:
                return False
            handlers.remove(handler)
            if not handlers:
                del self._subscribers[event_name]
            return True

    async def publish(self, event_name: str, payload: object | None = None) -> None:
        """Dispatch an event to every current subscriber without fail-fast behavior."""
        self._validate_event_name(event_name)
        with self._lock:
            handlers = tuple(self._subscribers.get(event_name, []))

        event = Event(name=event_name, payload=payload)
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                continue

    @staticmethod
    def _validate_event_name(event_name: object) -> None:
        if not isinstance(event_name, str) or not event_name.strip():
            raise InvalidEventNameError("Event names must be non-empty strings.")
