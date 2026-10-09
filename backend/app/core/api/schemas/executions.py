"""Typed request and response schemas for Execution Runtime endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_result import ExecutionResult
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus
from backend.app.core.execution_runtime.domain.lifecycle import RetryDecision
from backend.app.core.execution_runtime.domain.transition import ExecutionTransition


class ExecutionResultResponse(BaseModel):
    """External representation of a terminal execution result."""

    status: ExecutionStatus
    output: str | None
    duration: float | None
    logs: list[str]
    metadata: dict[str, object]

    @classmethod
    def from_result(cls, result: ExecutionResult) -> "ExecutionResultResponse":
        return cls(
            status=result.status,
            output=result.output,
            duration=result.duration,
            logs=list(result.logs),
            metadata=dict(result.metadata),
        )


class RetryInfoResponse(BaseModel):
    """Whether the server will accept a retry, and whether it must be acknowledged."""

    allowed: bool
    requires_acknowledgement: bool
    reason: str

    @classmethod
    def from_decision(cls, decision: RetryDecision) -> "RetryInfoResponse":
        return cls(
            allowed=decision.allowed,
            requires_acknowledgement=decision.requires_acknowledgement,
            reason=decision.reason,
        )


class ExecutionResponse(BaseModel):
    """External representation of a durable execution. Lease internals are not exposed."""

    execution_id: UUID
    agent_id: UUID
    status: ExecutionStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime | None
    duration: float | None
    result: ExecutionResultResponse | None
    error: str | None
    error_category: str | None
    current_step: str | None
    attempt: int
    retry_of: UUID | None
    retry: RetryInfoResponse | None
    metadata: dict[str, object]

    @classmethod
    def from_execution(cls, execution: Execution, retry: RetryDecision | None = None) -> "ExecutionResponse":
        return cls(
            execution_id=execution.execution_id,
            agent_id=execution.agent_id,
            status=execution.status,
            created_at=execution.created_at,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            updated_at=execution.updated_at,
            duration=execution.duration,
            result=(None if execution.result is None else ExecutionResultResponse.from_result(execution.result)),
            error=execution.error,
            error_category=execution.error_category,
            current_step=execution.current_step,
            attempt=execution.attempt,
            retry_of=execution.retry_of,
            retry=None if retry is None else RetryInfoResponse.from_decision(retry),
            metadata=dict(execution.metadata),
        )


class ExecutionListResponse(BaseModel):
    """A newest-first execution collection."""

    executions: list[ExecutionResponse]


class ExecutionCreateRequest(BaseModel):
    """Optional immutable metadata associated with an execution request."""

    metadata: dict[str, object] = Field(default_factory=dict)


class ExecutionRetryRequest(BaseModel):
    acknowledge_side_effects: bool = Field(
        default=False,
        description="Required to retry interrupted work that may already have had external effects.",
    )


class ExecutionTransitionResponse(BaseModel):
    sequence: int
    from_status: ExecutionStatus | None
    to_status: ExecutionStatus
    at: datetime
    detail: str | None

    @classmethod
    def from_domain(cls, transition: ExecutionTransition) -> "ExecutionTransitionResponse":
        return cls(
            sequence=transition.sequence,
            from_status=transition.from_status,
            to_status=transition.to_status,
            at=transition.at,
            detail=transition.detail,
        )


class ExecutionHistoryResponse(BaseModel):
    execution_id: UUID
    transitions: list[ExecutionTransitionResponse]
