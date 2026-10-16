"""Durable runtime events: the persisted, correlated subset of the in-process event stream."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from backend.app.core.observability.domain.events import Event


# Lifecycle events worth keeping across restarts. Logs, heartbeats, service registration and
# ``llm.requested`` stay in memory only: they are high volume and add nothing to a trace.
DURABLE_EVENT_PREFIXES = ("execution.", "workflow.", "task.", "approval.")
DURABLE_EVENT_TYPES = frozenset({"tool.rejected", "llm.completed", "llm.failed", "llm.retrying"})
MAX_STORED_PAYLOAD_BYTES = 8 * 1024
MAX_STORED_TEXT = 200  # event type, source

# Genesis identifiers that look like secrets to the key pattern below but aren't.
_IDENTIFIER_KEYS = frozenset({"session_id"})
_SECRET_KEY = re.compile(r"(pass(word|phrase)?|secret|token(?!s$)|api[_-]?key|apikey|auth|credential|private[_-]?key|cookie|session[_-]?id|bearer)", re.I)
_SECRET_VALUE = re.compile(r"(sk-[A-Za-z0-9_\-]{12,}|AIza[0-9A-Za-z_\-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abpr]-[A-Za-z0-9\-]{10,}|Bearer\s+\S{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
REDACTED = "[redacted]"


def is_durable(event_type: str) -> bool:
    return event_type in DURABLE_EVENT_TYPES or event_type.startswith(DURABLE_EVENT_PREFIXES)


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredEvent:
    """One persisted event with its correlation identifiers extracted into fields.

    ``sequence`` is assigned by storage and orders events across restarts. ``step_id`` is a
    workflow step; ``tool_task_id`` a tool task (workflow events call their step ``task_id``,
    tool and approval events use ``task_id`` for the tool task: the two are never confused).
    """

    event_id: str
    event_type: str
    source: str
    occurred_at: datetime
    payload: Mapping[str, object] = field(default_factory=dict)
    sequence: int | None = None
    execution_id: UUID | None = None
    interaction_id: UUID | None = None
    agent_id: UUID | None = None
    workflow_id: UUID | None = None
    step_id: str | None = None
    tool_task_id: UUID | None = None
    approval_id: UUID | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True, kw_only=True)
class EventQuery:
    """Filters for a page of stored events; all given filters must match."""

    execution_id: UUID | None = None  # also matches LLM calls of that interaction
    workflow_id: UUID | None = None
    approval_id: UUID | None = None
    tool_task_id: UUID | None = None
    event_type: str | None = None  # exact type, or a prefix ending in "." (e.g. "workflow.")


def matches(event: StoredEvent, query: EventQuery) -> bool:
    if query.execution_id is not None and query.execution_id not in (event.execution_id, event.interaction_id):
        return False
    if query.workflow_id is not None and event.workflow_id != query.workflow_id:
        return False
    if query.approval_id is not None and event.approval_id != query.approval_id:
        return False
    if query.tool_task_id is not None and event.tool_task_id != query.tool_task_id:
        return False
    if query.event_type is not None:
        prefix = query.event_type.endswith(".")
        if not (event.event_type.startswith(query.event_type) if prefix else event.event_type == query.event_type):
            return False
    return True


def stored_event(event: Event) -> StoredEvent:
    """Extract correlation identifiers and keep a redacted, size-bounded payload copy."""
    payload = event.payload
    task_id = payload.get("task_id")
    workflow_event = event.event_type.startswith("workflow.")
    return StoredEvent(
        event_id=str(event.id)[:64],
        event_type=event.event_type[:MAX_STORED_TEXT],
        source=str(event.source)[:MAX_STORED_TEXT],
        occurred_at=event.timestamp,
        payload=bounded_payload(payload),
        execution_id=_uuid(payload.get("execution_id")),
        interaction_id=_uuid(payload.get("interaction_id")),
        agent_id=_uuid(payload.get("agent_id")),
        workflow_id=_uuid(payload.get("workflow_id")),
        step_id=(str(task_id)[:200] if workflow_event and task_id is not None else _text(payload.get("workflow_task_id"))),
        tool_task_id=None if workflow_event else _uuid(task_id),
        approval_id=_uuid(payload.get("approval_id")),
    )


def bounded_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """A redacted copy; an oversized one is replaced by a marker rather than cut silently."""

    def walk(value: object, depth: int) -> object:
        if depth > 8:
            return "[nested too deeply]"
        if isinstance(value, Mapping):
            return {
                str(key): REDACTED if _secret_key(str(key)) and value[key] not in (None, "", [], {}) else walk(value[key], depth + 1)
                for key in value
            }
        if isinstance(value, (list, tuple)):
            return [walk(inner, depth + 1) for inner in value]
        if isinstance(value, str):
            return REDACTED if _SECRET_VALUE.search(value) else value
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return str(value)

    redacted = walk(payload, 0)
    if not isinstance(redacted, dict):
        return {}
    size = len(json.dumps(redacted, ensure_ascii=False, default=str).encode())
    if size > MAX_STORED_PAYLOAD_BYTES:
        return {"truncated": True, "bytes": size}
    return redacted


def _secret_key(key: str) -> bool:
    return key not in _IDENTIFIER_KEYS and _SECRET_KEY.search(key) is not None


def _uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _text(value: object) -> str | None:
    return value[:200] if isinstance(value, str) else None
