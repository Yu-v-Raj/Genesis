"""Approval Gateway: durable approval requests and approval-waiting states (Milestone 2).

Adds the ``approvals`` table, a ``waiting_approval`` status for executions, workflow
runs and workflow steps, and each step's ``approval_id``. Existing rows are unaffected.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
ACTIVE_ONLY = sa.text("state IN ('pending', 'approved')")

EXECUTION = ("pending", "queued", "starting", "running", "completed", "failed", "cancelled", "interrupted")
RUN = ("created", "queued", "running", "paused", "completed", "failed", "cancelled", "interrupted")
STEP = ("pending", "ready", "running", "completed", "failed", "cancelled", "blocked", "interrupted")
WAITING = "waiting_approval"


def _in(statuses: Sequence[str]) -> str:
    return "status IN (" + ", ".join(f"'{status}'" for status in statuses) + ")"


def _foreign_keys(enabled: bool) -> None:
    """SQLite only. Batch mode changes a constraint by recreating the table (copy, drop,
    rename). With foreign keys enforced, dropping a parent table (executions, workflow_runs)
    would cascade-delete every child row (execution timelines, workflow steps). So
    enforcement is switched off around the batch operations, confirmed off before anything
    changes, and the result is checked for broken references afterwards."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    bind.execute(sa.text(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}"))
    if not enabled and bind.execute(sa.text("PRAGMA foreign_keys")).scalar() != 0:
        # Inside a transaction SQLite ignores the PRAGMA; stop before any table is recreated.
        raise RuntimeError("Could not disable SQLite foreign keys for this migration; nothing was changed.")
    if enabled:
        broken = bind.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
        if broken:
            raise RuntimeError(f"Migration left {len(broken)} rows with broken references; it was not applied.")


def _replace_status_check(table: str, statuses: Sequence[str]) -> None:
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(op.f(f"ck_{table}_status"), type_="check")
        batch.create_check_constraint(op.f(f"ck_{table}_status"), _in(statuses))


def upgrade() -> None:
    _foreign_keys(False)
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("caller", sa.String(16), nullable=False),
        sa.Column("subject", JSON, nullable=False),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column("tool_version", sa.String(64), nullable=False),
        sa.Column("tool_contract", sa.String(64), nullable=False),
        sa.Column("arguments", JSON, nullable=False),
        sa.Column("operation_digest", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_source", sa.String(32), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
        sa.CheckConstraint(
            "state IN ('pending', 'approved', 'rejected', 'expired', 'consumed', 'cancelled')", name=op.f("ck_approvals_state")
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('completed', 'failed', 'unknown')", name=op.f("ck_approvals_outcome")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_approvals_version_positive")),
    )
    op.create_index("ix_approvals_state_created_at", "approvals", ["state", "created_at"])
    op.create_index(
        "uq_approvals_active_operation",
        "approvals",
        ["operation_digest"],
        unique=True,
        sqlite_where=ACTIVE_ONLY,
        postgresql_where=ACTIVE_ONLY,
    )
    _replace_status_check("executions", (*EXECUTION, WAITING))
    _replace_status_check("workflow_runs", (*RUN, WAITING))
    _replace_status_check("workflow_run_steps", (*STEP, WAITING))
    with op.batch_alter_table("workflow_run_steps") as batch:
        batch.add_column(sa.Column("approval_id", sa.Uuid(), nullable=True))
    _foreign_keys(True)


def downgrade() -> None:
    _foreign_keys(False)
    # Work still waiting for a decision can't be represented without these states: it is
    # cancelled (nothing ran while waiting), never silently resumed.
    op.execute(sa.text("UPDATE executions SET status = 'cancelled' WHERE status = 'waiting_approval'"))
    op.execute(sa.text("UPDATE workflow_runs SET status = 'cancelled' WHERE status = 'waiting_approval'"))
    op.execute(sa.text("UPDATE workflow_run_steps SET status = 'cancelled' WHERE status = 'waiting_approval'"))
    with op.batch_alter_table("workflow_run_steps") as batch:
        batch.drop_column("approval_id")
    _replace_status_check("workflow_run_steps", STEP)
    _replace_status_check("workflow_runs", RUN)
    _replace_status_check("executions", EXECUTION)
    op.drop_index("uq_approvals_active_operation", table_name="approvals")
    op.drop_index("ix_approvals_state_created_at", table_name="approvals")
    op.drop_table("approvals")
    _foreign_keys(True)
