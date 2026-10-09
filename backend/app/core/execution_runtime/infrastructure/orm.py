"""SQLAlchemy tables for durable executions and their timelines (persistence detail)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


JSONType = JSON().with_variant(JSONB(), "postgresql")
SerialId = BigInteger().with_variant(Integer(), "sqlite")
EXECUTION_STATUSES = "('pending', 'queued', 'starting', 'running', 'completed', 'failed', 'cancelled', 'interrupted')"


class ExecutionRow(Base):
    __tablename__ = "executions"
    __table_args__ = (
        CheckConstraint(f"status IN {EXECUTION_STATUSES}", name="status"),
        CheckConstraint("attempt >= 1", name="attempt_positive"),
        # Claiming scans QUEUED work oldest-first; history lists newest-first per Agent.
        Index("ix_executions_status_created_at", "status", "created_at"),
        Index("ix_executions_agent_id_created_at", "agent_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    agent_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("agents.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16))
    attempt: Mapped[int] = mapped_column(Integer)
    retry_of: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("executions.id", ondelete="SET NULL"))
    execution_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONType)
    current_step: Mapped[str | None] = mapped_column(String(100))
    result_output: Mapped[str | None] = mapped_column(Text)
    result_duration: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    error_category: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)


class ExecutionTransitionRow(Base):
    __tablename__ = "execution_transitions"
    __table_args__ = (
        UniqueConstraint("execution_id", "sequence", name="uq_execution_transitions_execution_sequence"),
    )

    id: Mapped[int] = mapped_column(SerialId, primary_key=True, autoincrement=True)
    execution_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("executions.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str | None] = mapped_column(Text)
