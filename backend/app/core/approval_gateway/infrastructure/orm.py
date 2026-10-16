"""SQLAlchemy table for approval requests (persistence detail)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


JSONType = JSON().with_variant(JSONB(), "postgresql")
APPROVAL_STATES = "('pending', 'approved', 'rejected', 'expired', 'consumed', 'cancelled')"
APPROVAL_OUTCOMES = "('completed', 'failed', 'unknown')"
# At most one pending-or-approved request per exact operation, enforced by the database.
ACTIVE_ONLY = text("state IN ('pending', 'approved')")


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(f"state IN {APPROVAL_STATES}", name="state"),
        CheckConstraint(f"outcome IS NULL OR outcome IN {APPROVAL_OUTCOMES}", name="outcome"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_approvals_state_created_at", "state", "created_at"),
        Index("ix_approvals_execution_id", "execution_id"),
        Index("ix_approvals_workflow_id", "workflow_id"),
        Index(
            "uq_approvals_active_operation",
            "operation_digest",
            unique=True,
            sqlite_where=ACTIVE_ONLY,
            postgresql_where=ACTIVE_ONLY,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    state: Mapped[str] = mapped_column(String(16))
    caller: Mapped[str] = mapped_column(String(16))
    subject: Mapped[dict[str, object]] = mapped_column(JSONType)
    # Copied from ``subject`` when the request is stored, so a trace can find them by index.
    execution_id: Mapped[UUID | None] = mapped_column(Uuid)
    workflow_id: Mapped[UUID | None] = mapped_column(Uuid)
    tool_name: Mapped[str] = mapped_column(String(200))
    tool_version: Mapped[str] = mapped_column(String(64))
    tool_contract: Mapped[str] = mapped_column(String(64))
    # The exact approved arguments; only redacted copies leave the backend.
    arguments: Mapped[dict[str, object]] = mapped_column(JSONType)
    operation_digest: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_source: Mapped[str | None] = mapped_column(String(32))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    task_id: Mapped[UUID | None] = mapped_column(Uuid)
    outcome: Mapped[str | None] = mapped_column(String(16))
    detail: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
