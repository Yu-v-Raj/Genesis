"""Typed request and response schemas for Execution Runtime endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_result import ExecutionResult
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus


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


class ExecutionResponse(BaseModel):
    """External representation of immutable execution metadata."""

    execution_id: UUID
    agent_id: UUID
    status: ExecutionStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration: float | None
    result: ExecutionResultResponse | None
    error: str | None
    metadata: dict[str, object]

    @classmethod
    def from_execution(cls, execution: Execution) -> "ExecutionResponse":
        return cls(
            execution_id=execution.execution_id,
            agent_id=execution.agent_id,
            status=execution.status,
            created_at=execution.created_at,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            duration=execution.duration,
            result=(None if execution.result is None else ExecutionResultResponse.from_result(execution.result)),
            error=execution.error,
            metadata=dict(execution.metadata),
        )


class ExecutionListResponse(BaseModel):
    """A newest-first execution collection."""

    executions: list[ExecutionResponse]


class ExecutionCreateRequest(BaseModel):
    """Optional immutable metadata associated with an execution request."""

    metadata: dict[str, object] = Field(default_factory=dict)
