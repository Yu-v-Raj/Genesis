"""Durable history: tool tasks, workflow run timelines, runtime events, approval lookups (Milestone 3).

Additive only. Three new tables, plus two nullable, indexed columns on ``approvals``
(``execution_id``, ``workflow_id``) copied from each request's ``subject``. No existing
table is recreated and no existing row is deleted or rewritten except for filling the two
new columns.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
SERIAL_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _foreign_keys(enabled: bool) -> None:
    """SQLite only. Nothing here recreates a table, so no cascade can fire; enforcement is
    still switched off around the changes (as in 0005) and the result is checked for
    broken references before the migration is accepted."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    bind.execute(sa.text(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}"))
    if not enabled and bind.execute(sa.text("PRAGMA foreign_keys")).scalar() != 0:
        raise RuntimeError("Could not disable SQLite foreign keys for this migration; nothing was changed.")
    if enabled:
        broken = bind.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
        if broken:
            raise RuntimeError(f"Migration left {len(broken)} rows with broken references; it was not applied.")


def _backfill_approval_links() -> None:
    """Copy execution and workflow ids out of each request's subject, through typed
    columns so the stored UUID format matches what the application writes."""
    bind = op.get_bind()
    approvals = sa.table(
        "approvals",
        sa.column("id", sa.Uuid()),
        sa.column("subject", JSON),
        sa.column("execution_id", sa.Uuid()),
        sa.column("workflow_id", sa.Uuid()),
    )
    for approval_id, subject in bind.execute(sa.select(approvals.c.id, approvals.c.subject)).all():
        links = {key: _uuid(subject, key) for key in ("execution_id", "workflow_id")}
        if any(value is not None for value in links.values()):
            bind.execute(sa.update(approvals).where(approvals.c.id == approval_id).values(**links))


def _uuid(subject: object, key: str) -> UUID | None:
    value = subject.get(key) if isinstance(subject, dict) else None
    try:
        return None if value is None else UUID(str(value))
    except ValueError:
        return None


def upgrade() -> None:
    _foreign_keys(False)
    op.create_table(
        "tool_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column("tool_version", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("caller", sa.String(16), nullable=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("interaction_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_task_id", sa.String(200), nullable=True),
        sa.Column("workflow_attempt", sa.Integer(), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arguments", JSON, nullable=False),
        sa.Column("metadata", JSON, nullable=False),
        sa.Column("result_status", sa.String(16), nullable=True),
        sa.Column("result_output", JSON, nullable=True),
        sa.Column("result_error", sa.Text(), nullable=True),
        sa.Column("result_metadata", JSON, nullable=True),
        sa.Column("result_logs", JSON, nullable=True),
        sa.Column("result_duration", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_tasks")),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed')", name=op.f("ck_tool_tasks_status")),
    )
    op.create_index("ix_tool_tasks_created_at", "tool_tasks", ["created_at"])
    op.create_index("ix_tool_tasks_execution_id_created_at", "tool_tasks", ["execution_id", "created_at"])
    op.create_index("ix_tool_tasks_workflow_id_created_at", "tool_tasks", ["workflow_id", "created_at"])
    op.create_index("ix_tool_tasks_approval_id", "tool_tasks", ["approval_id"])
    op.create_index("ix_tool_tasks_status", "tool_tasks", ["status"])

    op.create_table(
        "workflow_run_transitions",
        sa.Column("id", SERIAL_ID, autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.String(200), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worker", sa.String(200), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["workflow_runs.id"], name=op.f("fk_workflow_run_transitions_run_id_workflow_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_run_transitions")),
        sa.UniqueConstraint("run_id", "sequence", name="uq_workflow_run_transitions_run_sequence"),
    )

    op.create_table(
        "runtime_events",
        sa.Column("sequence", SERIAL_ID, autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("interaction_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
        sa.Column("step_id", sa.String(200), nullable=True),
        sa.Column("tool_task_id", sa.Uuid(), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("payload", JSON, nullable=False),
        sa.PrimaryKeyConstraint("sequence", name=op.f("pk_runtime_events")),
        sa.UniqueConstraint("event_id", name=op.f("uq_runtime_events_event_id")),
    )
    op.create_index("ix_runtime_events_occurred_at", "runtime_events", ["occurred_at"])
    op.create_index("ix_runtime_events_event_type_sequence", "runtime_events", ["event_type", "sequence"])
    op.create_index("ix_runtime_events_execution_id_sequence", "runtime_events", ["execution_id", "sequence"])
    op.create_index("ix_runtime_events_interaction_id_sequence", "runtime_events", ["interaction_id", "sequence"])
    op.create_index("ix_runtime_events_workflow_id_sequence", "runtime_events", ["workflow_id", "sequence"])
    op.create_index("ix_runtime_events_tool_task_id", "runtime_events", ["tool_task_id"])
    op.create_index("ix_runtime_events_approval_id", "runtime_events", ["approval_id"])

    # Plain ADD COLUMN (nullable, no default): the approvals table is not recreated.
    op.add_column("approvals", sa.Column("execution_id", sa.Uuid(), nullable=True))
    op.add_column("approvals", sa.Column("workflow_id", sa.Uuid(), nullable=True))
    _backfill_approval_links()
    op.create_index("ix_approvals_execution_id", "approvals", ["execution_id"])
    op.create_index("ix_approvals_workflow_id", "approvals", ["workflow_id"])
    _foreign_keys(True)


def downgrade() -> None:
    """Removes the new history tables (their rows are lost: they did not exist before
    0006) and the two copied approval columns (the ids remain in ``subject``)."""
    _foreign_keys(False)
    op.drop_index("ix_approvals_workflow_id", table_name="approvals")
    op.drop_index("ix_approvals_execution_id", table_name="approvals")
    if op.get_bind().dialect.name == "sqlite":
        # Native DROP COLUMN (SQLite 3.35+) instead of batch mode, so the approvals table
        # and its partial unique index are never recreated.
        op.execute(sa.text("ALTER TABLE approvals DROP COLUMN workflow_id"))
        op.execute(sa.text("ALTER TABLE approvals DROP COLUMN execution_id"))
    else:
        op.drop_column("approvals", "workflow_id")
        op.drop_column("approvals", "execution_id")
    for index in (
        "ix_runtime_events_approval_id",
        "ix_runtime_events_tool_task_id",
        "ix_runtime_events_workflow_id_sequence",
        "ix_runtime_events_interaction_id_sequence",
        "ix_runtime_events_execution_id_sequence",
        "ix_runtime_events_event_type_sequence",
        "ix_runtime_events_occurred_at",
    ):
        op.drop_index(index, table_name="runtime_events")
    op.drop_table("runtime_events")
    op.drop_table("workflow_run_transitions")
    for index in (
        "ix_tool_tasks_status",
        "ix_tool_tasks_approval_id",
        "ix_tool_tasks_workflow_id_created_at",
        "ix_tool_tasks_execution_id_created_at",
        "ix_tool_tasks_created_at",
    ):
        op.drop_index(index, table_name="tool_tasks")
    op.drop_table("tool_tasks")
    _foreign_keys(True)
