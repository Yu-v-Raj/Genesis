"""Persistent Agent definitions and conversation sessions (v0.11).

Revision ID: 0001
Revises:
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
MESSAGE_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("tags", JSON, nullable=False),
        sa.Column("metadata", JSON, nullable=False),
        sa.Column("llm_provider", sa.String(100), nullable=True),
        sa.Column("llm_model_name", sa.String(200), nullable=True),
        sa.Column("allowed_tools", JSON, nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_agents"),
        sa.CheckConstraint("status IN ('created', 'idle', 'stopped')", name="ck_agents_status"),
        sa.CheckConstraint(
            "(llm_provider IS NULL) = (llm_model_name IS NULL)", name="ck_agents_llm_model_complete"
        ),
    )
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_agent_sessions"),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name="fk_agent_sessions_agent_id_agents", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_agent_sessions_agent_id_updated_at", "agent_sessions", ["agent_id", "updated_at"])
    op.create_table(
        "agent_session_messages",
        sa.Column("id", MESSAGE_ID, autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("interaction_id", sa.String(36), nullable=True),
        sa.Column("tool_call_id", sa.String(200), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("tool_status", sa.String(32), nullable=True),
        sa.Column("tool_calls", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_agent_session_messages"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name="fk_agent_session_messages_session_id_agent_sessions",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("session_id", "position", name="uq_agent_session_messages_session_position"),
        sa.CheckConstraint("role IN ('user', 'assistant', 'tool')", name="ck_agent_session_messages_role"),
    )


def downgrade() -> None:
    op.drop_table("agent_session_messages")
    op.drop_index("ix_agent_sessions_agent_id_updated_at", table_name="agent_sessions")
    op.drop_table("agent_sessions")
    op.drop_table("agents")
