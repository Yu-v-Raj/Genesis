"""Bounded in-memory event history adapter."""

from collections import deque
from threading import RLock

from backend.app.core.observability.domain.events import Event


class EventHistory:
    """Store recent events in a thread-safe circular buffer."""

    def __init__(self, capacity: int = 1000) -> None:
        if capacity < 1:
            raise ValueError("Event history capacity must be at least one.")
        self._events: deque[Event] = deque(maxlen=capacity)
        self._lock = RLock()

    def record(self, event: Event) -> None:
        """Append an event, discarding the oldest event when at capacity."""
        with self._lock:
            self._events.append(event)

    def recent(self, limit: int | None = None) -> tuple[Event, ...]:
        """Return recent events newest-first, optionally limited in count."""
        with self._lock:
            events = tuple(reversed(self._events))
        return events if limit is None else events[:limit]

    def latest(self) -> Event | None:
        """Return the most recently recorded event, if one exists."""
        with self._lock:
            return self._events[-1] if self._events else None

    def event_types(self) -> tuple[str, ...]:
        """Return currently retained event types in deterministic order."""
        with self._lock:
            return tuple(sorted({event.event_type for event in self._events}))

    def by_type(self, event_type: str, limit: int | None = None) -> tuple[Event, ...]:
        """Return recent events that match ``event_type``."""
        return tuple(event for event in self.recent(limit=None) if event.event_type == event_type)[
            :limit
        ]
