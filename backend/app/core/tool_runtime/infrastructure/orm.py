"""SQLAlchemy table for tool task history (persistence detail)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


JSONType = JSON().with_variant(JSONB(), "postgresql")
TASK_STATUSES = "('pending', 'running', 'completed', 'failed')"


class ToolTaskRow(Base):
    """One tool invocation. Correlation columns come from the trusted execution context."""

    __tablename__ = "tool_tasks"
    __table_args__ = (
        CheckConstraint(f"status IN {TASK_STATUSES}", name="status"),
        Index("ix_tool_tasks_created_at", "created_at"),
        Index("ix_tool_tasks_execution_id_created_at", "execution_id", "created_at"),
        Index("ix_tool_tasks_workflow_id_created_at", "workflow_id", "created_at"),
        Index("ix_tool_tasks_approval_id", "approval_id"),
        Index("ix_tool_tasks_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(200))
    tool_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    caller: Mapped[str | None] = mapped_column(String(16))
    execution_id: Mapped[UUID | None] = mapped_column(Uuid)
    agent_id: Mapped[UUID | None] = mapped_column(Uuid)
    interaction_id: Mapped[UUID | None] = mapped_column(Uuid)
    workflow_id: Mapped[UUID | None] = mapped_column(Uuid)
    workflow_task_id: Mapped[str | None] = mapped_column(String(200))
    workflow_attempt: Mapped[int | None] = mapped_column(Integer)
    approval_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Redacted display copy of the arguments, and the trusted task metadata.
    arguments: Mapped[dict[str, object]] = mapped_column(JSONType)
    task_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONType)
    # Bounded result: large outputs are stored as a marked preview, never in full.
    result_status: Mapped[str | None] = mapped_column(String(16))
    result_output: Mapped[object | None] = mapped_column(JSONType)
    result_error: Mapped[str | None] = mapped_column(Text)
    result_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONType)
    result_logs: Mapped[list[str] | None] = mapped_column(JSONType)
    result_duration: Mapped[float | None] = mapped_column(Float)
