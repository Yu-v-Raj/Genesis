"""SQLAlchemy table for Agent memories (persistence detail of the Memory Runtime)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


JSONType = JSON().with_variant(JSONB(), "postgresql")


class MemoryRow(Base):
    __tablename__ = "agent_memories"
    __table_args__ = (
        CheckConstraint("kind IN ('fact', 'note', 'preference', 'context')", name="kind"),
        # Memories are always read per Agent, newest first.
        Index("ix_agent_memories_agent_id_created_at", "agent_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # A memory belongs to exactly one Agent and is deleted with it.
    agent_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("agents.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))
    memory_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONType)
    tags: Mapped[list[str]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
