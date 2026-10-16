"""SQLAlchemy table for durable runtime events (persistence detail)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


JSONType = JSON().with_variant(JSONB(), "postgresql")
SerialId = BigInteger().with_variant(Integer(), "sqlite")


class RuntimeEventRow(Base):
    """One lifecycle event. ``sequence`` orders events across restarts and pages them."""

    __tablename__ = "runtime_events"
    __table_args__ = (
        Index("ix_runtime_events_occurred_at", "occurred_at"),
        Index("ix_runtime_events_event_type_sequence", "event_type", "sequence"),
        Index("ix_runtime_events_execution_id_sequence", "execution_id", "sequence"),
        Index("ix_runtime_events_interaction_id_sequence", "interaction_id", "sequence"),
        Index("ix_runtime_events_workflow_id_sequence", "workflow_id", "sequence"),
        Index("ix_runtime_events_tool_task_id", "tool_task_id"),
        Index("ix_runtime_events_approval_id", "approval_id"),
    )

    sequence: Mapped[int] = mapped_column(SerialId, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(200))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    execution_id: Mapped[UUID | None] = mapped_column(Uuid)
    interaction_id: Mapped[UUID | None] = mapped_column(Uuid)
    agent_id: Mapped[UUID | None] = mapped_column(Uuid)
    workflow_id: Mapped[UUID | None] = mapped_column(Uuid)
    step_id: Mapped[str | None] = mapped_column(String(200))
    tool_task_id: Mapped[UUID | None] = mapped_column(Uuid)
    approval_id: Mapped[UUID | None] = mapped_column(Uuid)
    # Redacted and bounded (see runtime_event.bounded_payload).
    payload: Mapped[dict[str, object]] = mapped_column(JSONType)
