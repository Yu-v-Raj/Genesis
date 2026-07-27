"""Read-only endpoints for Genesis event and log observability."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.core.api.dependencies.system import get_event_history
from backend.app.core.api.schemas.observability import (
    EventListResponse,
    EventResponse,
    EventTypesResponse,
    LatestEventResponse,
)
from backend.app.core.observability.domain.events import LOG_CREATED_EVENT_TYPE
from backend.app.core.observability.infrastructure.event_history import EventHistory


router = APIRouter(tags=["observability"])
EventLimit = Annotated[int, Query(ge=1, le=1000)]


@router.get("/api/events", response_model=EventListResponse)
def recent_events(
    history: Annotated[EventHistory, Depends(get_event_history)],
    limit: EventLimit = 100,
) -> EventListResponse:
    """Return the most recent retained events, newest first."""
    return EventListResponse(events=[EventResponse.from_event(event) for event in history.recent(limit)])


@router.get("/api/events/latest", response_model=LatestEventResponse)
def latest_event(
    history: Annotated[EventHistory, Depends(get_event_history)],
) -> LatestEventResponse:
    """Return the latest retained event, if any."""
    event = history.latest()
    return LatestEventResponse(event=None if event is None else EventResponse.from_event(event))


@router.get("/api/events/types", response_model=EventTypesResponse)
def event_types(
    history: Annotated[EventHistory, Depends(get_event_history)],
) -> EventTypesResponse:
    """Return event types represented in the retained history."""
    return EventTypesResponse(event_types=list(history.event_types()))


@router.get("/api/logs", response_model=EventListResponse)
def logs(
    history: Annotated[EventHistory, Depends(get_event_history)],
    limit: EventLimit = 100,
) -> EventListResponse:
    """Return recent structured log events."""
    return EventListResponse(
        events=[
            EventResponse.from_event(event)
            for event in history.by_type(LOG_CREATED_EVENT_TYPE, limit)
        ]
    )


@router.get("/api/logs/errors", response_model=EventListResponse)
def error_logs(
    history: Annotated[EventHistory, Depends(get_event_history)],
    limit: EventLimit = 100,
) -> EventListResponse:
    """Return recent ERROR and CRITICAL structured log events."""
    events = (
        event
        for event in history.by_type(LOG_CREATED_EVENT_TYPE)
        if event.payload.get("level") in {"ERROR", "CRITICAL"}
    )
    return EventListResponse(events=[EventResponse.from_event(event) for event in list(events)[:limit]])
