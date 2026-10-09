"""SQLAlchemy tables for workflow definitions, runs, and run steps (persistence detail)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


JSONType = JSON().with_variant(JSONB(), "postgresql")
RUN_STATUSES = "('created', 'queued', 'running', 'paused', 'completed', 'failed', 'cancelled', 'interrupted')"
STEP_STATUSES = "('pending', 'ready', 'running', 'completed', 'failed', 'cancelled', 'blocked', 'interrupted')"


class WorkflowDefinitionRow(Base):
    """One immutable version of a definition; (id, version) is the key."""

    __tablename__ = "workflow_definitions"
    __table_args__ = (CheckConstraint("version >= 1", name="version_positive"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    definition_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONType)
    # Step definitions: task_id, name, action, configuration, dependencies, metadata.
    steps: Mapped[list[dict[str, object]]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkflowRunRow(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(f"status IN {RUN_STATUSES}", name="status"),
        CheckConstraint("attempt >= 1", name="attempt_positive"),
        ForeignKeyConstraint(
            ["definition_id", "definition_version"],
            ["workflow_definitions.id", "workflow_definitions.version"],
            name="fk_workflow_runs_definition_workflow_definitions",
        ),
        Index("ix_workflow_runs_status_created_at", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    definition_id: Mapped[UUID | None] = mapped_column(Uuid)
    definition_version: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    attempt: Mapped[int] = mapped_column(Integer)
    run_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONType)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)


class WorkflowRunStepRow(Base):
    __tablename__ = "workflow_run_steps"
    __table_args__ = (CheckConstraint(f"status IN {STEP_STATUSES}", name="status"),)

    run_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workflow_runs.id", ondelete="CASCADE"), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(32))
    configuration: Mapped[dict[str, object]] = mapped_column(JSONType)
    dependencies: Mapped[list[str]] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[object | None] = mapped_column(JSONType)
    error: Mapped[str | None] = mapped_column(Text)
    step_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONType)
