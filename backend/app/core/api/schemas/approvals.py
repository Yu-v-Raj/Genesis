"""Typed contracts for the Approval Gateway API. Arguments are always the redacted copy."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.app.core.api.schemas.tools import TaskResponse


class ApprovalSubjectResponse(BaseModel):
    """Who asked, from the request's real execution context (names are looked up, not stored)."""

    agent_id: UUID | None = None
    agent_name: str | None = None
    execution_id: UUID | None = None
    workflow_id: UUID | None = None
    workflow_name: str | None = None
    step_id: str | None = None
    step_name: str | None = None
    attempt: int | None = None


class ApprovalResponse(BaseModel):
    approval_id: UUID
    state: str
    caller: str
    tool_name: str
    # The registered tool's own description; None if the tool is no longer registered.
    tool_description: str | None
    tool_version: str
    reason: str
    arguments: dict[str, object]
    redacted_fields: list[str]
    subject: ApprovalSubjectResponse
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    decision_source: str | None
    consumed_at: datetime | None
    task_id: UUID | None
    outcome: str | None
    detail: str | None
    # What the server will accept next; the console never decides this on its own.
    can_decide: bool
    can_cancel: bool
    can_run: bool


class ApprovalListResponse(BaseModel):
    approvals: list[ApprovalResponse]
    pending_count: int


class ApprovalActionResponse(BaseModel):
    """The stored request after an action, and for operator tests the run it caused."""

    approval: ApprovalResponse
    task: TaskResponse | None = None
    # Why an approved operator test did not run (e.g. the tool was disabled meanwhile).
    problem: str | None = None
