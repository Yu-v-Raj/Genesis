"""Persistence port for durable runtime events, and a process-local implementation."""

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import replace
from datetime import datetime
from threading import RLock

from backend.app.core.observability.domain.runtime_event import EventQuery, StoredEvent, matches


class RuntimeEventStore(ABC):
    @abstractmethod
    async def append(self, events: tuple[StoredEvent, ...]) -> None:
        """Store events in order; storage assigns each a increasing ``sequence``."""

    @abstractmethod
    async def page(self, query: EventQuery, *, before_sequence: int | None, limit: int) -> tuple[StoredEvent, ...]:
        """Matching events newest first, older than ``before_sequence`` when given."""

    @abstractmethod
    async def prune(self, older_than: datetime) -> int:
        """Delete events that occurred before ``older_than``; returns how many."""


class InMemoryRuntimeEventStore(RuntimeEventStore):
    def __init__(self, capacity: int = 10_000) -> None:
        self._events: deque[StoredEvent] = deque(maxlen=capacity)
        self._next = 1
        self._lock = RLock()

    async def append(self, events: tuple[StoredEvent, ...]) -> None:
        with self._lock:
            for event in events:
                self._events.append(replace(event, sequence=self._next))
                self._next += 1

    async def page(self, query: EventQuery, *, before_sequence: int | None, limit: int) -> tuple[StoredEvent, ...]:
        with self._lock:
            newest = tuple(reversed(self._events))
        found = (e for e in newest if (before_sequence is None or (e.sequence or 0) < before_sequence) and matches(e, query))
        return tuple(event for _, event in zip(range(limit), found))

    async def prune(self, older_than: datetime) -> int:
        with self._lock:
            kept = [event for event in self._events if event.occurred_at >= older_than]
            removed = len(self._events) - len(kept)
            self._events = deque(kept, maxlen=self._events.maxlen)
        return removed
