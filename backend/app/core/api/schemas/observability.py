"""Pydantic models for read-only observability API responses."""

from datetime import datetime

from pydantic import BaseModel

from backend.app.core.observability.domain.events import Event


class EventResponse(BaseModel):
    """Externally safe representation of a Genesis event."""

    id: str
    timestamp: datetime
    event_type: str
    source: str
    payload: dict[str, object]

    @classmethod
    def from_event(cls, event: Event) -> "EventResponse":
        """Create an API response model from a Core event."""
        return cls(
            id=event.id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            source=event.source,
            payload=dict(event.payload),
        )


class EventListResponse(BaseModel):
    """A collection of recent Genesis events."""

    events: list[EventResponse]


class LatestEventResponse(BaseModel):
    """The latest Genesis event, when the history is non-empty."""

    event: EventResponse | None


class EventTypesResponse(BaseModel):
    """The event types represented in the retained history."""

    event_types: list[str]
