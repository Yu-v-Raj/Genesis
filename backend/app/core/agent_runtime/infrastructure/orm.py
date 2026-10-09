"""SQLAlchemy tables for Agent definitions and conversation sessions.

These classes are persistence details: they never leave this package. The repositories
translate them to and from the frozen domain records.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
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
# SQLite only auto-increments INTEGER PRIMARY KEY; PostgreSQL gets a 64-bit identity.
MessageIdType = BigInteger().with_variant(Integer(), "sqlite")


class AgentRow(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("status IN ('created', 'idle', 'stopped')", name="status"),
        CheckConstraint(
            "(llm_provider IS NULL) = (llm_model_name IS NULL)", name="llm_model_complete"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(100))
    # Restoration category only (see AgentRegistry); never "running".
    status: Mapped[str] = mapped_column(String(16))
    tags: Mapped[list[str]] = mapped_column(JSONType)
    agent_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONType)
    llm_provider: Mapped[str | None] = mapped_column(String(100))
    llm_model_name: Mapped[str | None] = mapped_column(String(200))
    allowed_tools: Mapped[list[str]] = mapped_column(JSONType)
    instructions: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Optimistic concurrency: an UPDATE that matches no row at the expected version fails.
    version: Mapped[int] = mapped_column(Integer)

    __mapper_args__ = {"version_id_col": version}


class SessionRow(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (Index("ix_agent_sessions_agent_id_updated_at", "agent_id", "updated_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    agent_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("agents.id", ondelete="CASCADE"))
    message_count: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MessageRow(Base):
    __tablename__ = "agent_session_messages"
    __table_args__ = (
        # Ordering key and the guard against two writers claiming the same slot.
        UniqueConstraint("session_id", "position", name="uq_agent_session_messages_session_position"),
        CheckConstraint("role IN ('user', 'assistant', 'tool')", name="role"),
    )

    id: Mapped[int] = mapped_column(MessageIdType, primary_key=True, autoincrement=True)
    session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("agent_sessions.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    interaction_id: Mapped[str | None] = mapped_column(String(36))
    tool_call_id: Mapped[str | None] = mapped_column(String(200))
    tool_name: Mapped[str | None] = mapped_column(String(100))
    tool_status: Mapped[str | None] = mapped_column(String(32))
    # Full tool calls (with arguments) are needed to replay history to the LLM; the API
    # never returns this column.
    tool_calls: Mapped[list[dict[str, object]] | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
