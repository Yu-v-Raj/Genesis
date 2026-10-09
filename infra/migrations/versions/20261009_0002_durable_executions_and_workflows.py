"""Durable executions, execution timelines, workflow definitions, runs, and steps (v0.12).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
SERIAL_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table('workflow_definitions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('metadata', JSON, nullable=False),
    sa.Column('steps', JSON, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('version >= 1', name=op.f('ck_workflow_definitions_version_positive')),
    sa.PrimaryKeyConstraint('id', 'version', name=op.f('pk_workflow_definitions'))
    )
    op.create_table('executions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('agent_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('retry_of', sa.Uuid(), nullable=True),
    sa.Column('metadata', JSON, nullable=False),
    sa.Column('current_step', sa.String(length=100), nullable=True),
    sa.Column('result_output', sa.Text(), nullable=True),
    sa.Column('result_duration', sa.Float(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('error_category', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('lease_owner', sa.String(length=200), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'queued', 'starting', 'running', 'completed', 'failed', 'cancelled', 'interrupted')", name=op.f('ck_executions_status')),
    sa.CheckConstraint('attempt >= 1', name=op.f('ck_executions_attempt_positive')),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], name=op.f('fk_executions_agent_id_agents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['retry_of'], ['executions.id'], name=op.f('fk_executions_retry_of_executions'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_executions'))
    )
    op.create_index('ix_executions_agent_id_created_at', 'executions', ['agent_id', 'created_at'])
    op.create_index('ix_executions_status_created_at', 'executions', ['status', 'created_at'])

    op.create_table('workflow_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('definition_id', sa.Uuid(), nullable=True),
    sa.Column('definition_version', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('metadata', JSON, nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('lease_owner', sa.String(length=200), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint("status IN ('created', 'queued', 'running', 'paused', 'completed', 'failed', 'cancelled', 'interrupted')", name=op.f('ck_workflow_runs_status')),
    sa.CheckConstraint('attempt >= 1', name=op.f('ck_workflow_runs_attempt_positive')),
    sa.ForeignKeyConstraint(['definition_id', 'definition_version'], ['workflow_definitions.id', 'workflow_definitions.version'], name='fk_workflow_runs_definition_workflow_definitions'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_runs'))
    )
    op.create_index('ix_workflow_runs_status_created_at', 'workflow_runs', ['status', 'created_at'])

    op.create_table('execution_transitions',
    sa.Column('id', SERIAL_ID, autoincrement=True, nullable=False),
    sa.Column('execution_id', sa.Uuid(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('from_status', sa.String(length=16), nullable=True),
    sa.Column('to_status', sa.String(length=16), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], name=op.f('fk_execution_transitions_execution_id_executions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_execution_transitions')),
    sa.UniqueConstraint('execution_id', 'sequence', name='uq_execution_transitions_execution_sequence')
    )
    op.create_table('workflow_run_steps',
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('task_id', sa.String(length=200), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('action', sa.String(length=32), nullable=False),
    sa.Column('configuration', JSON, nullable=False),
    sa.Column('dependencies', JSON, nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('result', JSON, nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('metadata', JSON, nullable=False),
    sa.CheckConstraint("status IN ('pending', 'ready', 'running', 'completed', 'failed', 'cancelled', 'blocked', 'interrupted')", name=op.f('ck_workflow_run_steps_status')),
    sa.ForeignKeyConstraint(['run_id'], ['workflow_runs.id'], name=op.f('fk_workflow_run_steps_run_id_workflow_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('run_id', 'task_id', name=op.f('pk_workflow_run_steps'))
    )


def downgrade() -> None:
    op.drop_table('workflow_run_steps')
    op.drop_table('execution_transitions')
    op.drop_index('ix_workflow_runs_status_created_at', table_name='workflow_runs')
    op.drop_table('workflow_runs')
    op.drop_index('ix_executions_status_created_at', table_name='executions')
    op.drop_index('ix_executions_agent_id_created_at', table_name='executions')
    op.drop_table('executions')
    op.drop_table('workflow_definitions')
