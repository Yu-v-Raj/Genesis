"""Typed contracts for Operations traces and durable runtime events."""

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.app.core.api.schemas.approvals import ApprovalResponse
from backend.app.core.api.schemas.executions import ExecutionResponse, ExecutionTransitionResponse
from backend.app.core.api.schemas.tools import TaskResponse
from backend.app.core.api.schemas.workflows import WorkflowResponse
from backend.app.core.observability.domain.runtime_event import StoredEvent
from backend.app.core.workflow_runtime.domain.transition import WorkflowTransition


class RuntimeEventResponse(BaseModel):
    """A persisted event; the payload is redacted and size-bounded when stored."""

    sequence: int
    event_id: str
    event_type: str
    source: str
    occurred_at: datetime
    payload: dict[str, object]
    execution_id: UUID | None
    interaction_id: UUID | None
    agent_id: UUID | None
    workflow_id: UUID | None
    step_id: str | None
    tool_task_id: UUID | None
    approval_id: UUID | None

    @classmethod
    def from_stored(cls, event: StoredEvent) -> "RuntimeEventResponse":
        return cls(
            sequence=event.sequence or 0,
            event_id=event.event_id,
            event_type=event.event_type,
            source=event.source,
            occurred_at=event.occurred_at,
            payload=dict(event.payload),
            execution_id=event.execution_id,
            interaction_id=event.interaction_id,
            agent_id=event.agent_id,
            workflow_id=event.workflow_id,
            step_id=event.step_id,
            tool_task_id=event.tool_task_id,
            approval_id=event.approval_id,
        )


class RuntimeEventPageResponse(BaseModel):
    """Newest first. Pass ``next_before_sequence`` as ``before_sequence`` for older events."""

    events: list[RuntimeEventResponse]
    next_before_sequence: int | None


class ModelCallResponse(BaseModel):
    """One model call, from its ``llm.completed`` or ``llm.failed`` event. Never content."""

    sequence: int
    at: datetime
    outcome: str  # "completed" or "failed"
    provider: str | None
    model: str | None
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    error_type: str | None
    # Requests made for this call (1 = no retry); None for calls recorded before retries existed.
    attempts: int | None = None
    error_category: str | None = None  # e.g. rate_limited, provider_unavailable, timeout, cancelled

    @classmethod
    def from_stored(cls, event: StoredEvent) -> "ModelCallResponse":
        payload = event.payload
        found = payload.get("usage")
        usage: Mapping[str, object] = found if isinstance(found, Mapping) else {}
        return cls(
            sequence=event.sequence or 0,
            at=event.occurred_at,
            outcome="completed" if event.event_type == "llm.completed" else "failed",
            provider=_text(payload.get("provider")),
            model=_text(payload.get("model")),
            duration_ms=_int(payload.get("duration_ms")),
            input_tokens=_int(usage.get("input_tokens")),
            output_tokens=_int(usage.get("output_tokens")),
            total_tokens=_int(usage.get("total_tokens")),
            error_type=_text(payload.get("error_type")),
            attempts=_int(payload.get("attempts")),
            error_category=_text(payload.get("error_category")),
        )


class WorkflowTransitionResponse(BaseModel):
    sequence: int
    step_id: str | None  # None: the run itself changed status
    attempt: int
    from_status: str | None
    to_status: str
    at: datetime
    worker: str | None
    detail: str | None

    @classmethod
    def from_domain(cls, transition: WorkflowTransition) -> "WorkflowTransitionResponse":
        return cls(
            sequence=transition.sequence,
            step_id=transition.step_id,
            attempt=transition.attempt,
            from_status=transition.from_status,
            to_status=transition.to_status,
            at=transition.at,
            worker=transition.worker,
            detail=transition.detail,
        )


class TraceLimits(BaseModel):
    """True where a list was cut to its most recent entries."""

    tool_tasks: bool
    approvals: bool
    events: bool


class ExecutionTraceResponse(BaseModel):
    execution: ExecutionResponse
    transitions: list[ExecutionTransitionResponse]
    model_calls: list[ModelCallResponse]
    tool_tasks: list[TaskResponse]
    approvals: list[ApprovalResponse]
    events: list[RuntimeEventResponse]  # oldest first
    truncated: TraceLimits


class WorkflowTraceResponse(BaseModel):
    run: WorkflowResponse
    transitions: list[WorkflowTransitionResponse]
    tool_tasks: list[TaskResponse]
    approvals: list[ApprovalResponse]
    events: list[RuntimeEventResponse]  # oldest first
    truncated: TraceLimits


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
