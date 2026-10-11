"""Durable Agent memories, deleted with their Agent (v0.13).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("metadata", JSON, nullable=False),
        sa.Column("tags", JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_agent_memories"),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name="fk_agent_memories_agent_id_agents", ondelete="CASCADE"
        ),
        sa.CheckConstraint("kind IN ('fact', 'note', 'preference', 'context')", name="ck_agent_memories_kind"),
    )
    op.create_index("ix_agent_memories_agent_id_created_at", "agent_memories", ["agent_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_memories_agent_id_created_at", table_name="agent_memories")
    op.drop_table("agent_memories")
