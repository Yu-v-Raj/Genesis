"""Migration 0006 is additive: every existing row survives upgrade, downgrade and upgrade.

Seeds a database at 0005 with Agents, sessions, memories, executions and their timelines,
workflow definitions, runs and steps, and approval requests (one for an Agent execution,
one for a workflow step, one operator test), then checks row counts, row contents, the
approval backfill, the approvals partial unique index and SQLite foreign keys at each step.
"""

import sqlite3
from pathlib import Path

from alembic import command

from backend.app.database.migrations import alembic_config

AGENT, SESSION, EXECUTION, DEFINITION, RUN = "a" * 32, "b" * 32, "e" * 32, "d" * 32, "f" * 32
AGENT_APPROVAL, STEP_APPROVAL, OPERATOR_APPROVAL = "1" * 32, "2" * 32, "3" * 32
EXECUTION_DASHED = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
RUN_DASHED = "ffffffff-ffff-ffff-ffff-ffffffffffff"
NOW = "2026-10-16 10:00:00.000000"
LATER = "2026-10-17 10:00:00.000000"
EXISTING = (
    "agents", "agent_sessions", "agent_session_messages", "agent_memories", "executions", "execution_transitions",
    "workflow_definitions", "workflow_runs", "workflow_run_steps", "approvals",
)
NEW = ("tool_tasks", "workflow_run_transitions", "runtime_events")


def _approval(approval_id: str, caller: str, subject: str, digest: str, state: str) -> tuple[str, ...]:
    return (approval_id, state, caller, subject, "simulated_action", "1.0.0", "c" * 64, '{"value": "x"}', digest, "why", NOW, LATER)


def _seed(path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO agents (id, name, description, type, status, tags, metadata, allowed_tools, instructions, created_at, updated_at, version) "
        "VALUES (?, 'A', 'd', 't', 'idle', '[]', '{}', '[\"echo\"]', 'be kind', ?, ?, 1)",
        (AGENT, NOW, NOW),
    )
    db.execute(
        "INSERT INTO agent_sessions (id, agent_id, message_count, title, created_at, updated_at) VALUES (?, ?, 2, 'Hello', ?, ?)",
        (SESSION, AGENT, NOW, NOW),
    )
    db.executemany(
        "INSERT INTO agent_session_messages (session_id, position, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        [(SESSION, 0, "user", "hello", NOW), (SESSION, 1, "assistant", "hi", NOW)],
    )
    db.execute(
        "INSERT INTO agent_memories (id, agent_id, content, kind, metadata, tags, created_at, updated_at) VALUES (?, ?, 'likes tea', 'fact', '{}', '[]', ?, ?)",
        ("9" * 32, AGENT, NOW, NOW),
    )
    db.execute(
        "INSERT INTO executions (id, agent_id, status, attempt, metadata, checkpoint, created_at, updated_at, version) "
        "VALUES (?, ?, 'waiting_approval', 1, '{}', '{\"turn\": 1}', ?, ?, 3)",
        (EXECUTION, AGENT, NOW, NOW),
    )
    db.executemany(
        "INSERT INTO execution_transitions (execution_id, sequence, from_status, to_status, at) VALUES (?, ?, ?, ?, ?)",
        [(EXECUTION, 1, None, "pending", NOW), (EXECUTION, 2, "pending", "queued", NOW), (EXECUTION, 3, "queued", "waiting_approval", NOW)],
    )
    db.execute(
        "INSERT INTO workflow_definitions (id, version, name, description, metadata, steps, created_at) VALUES (?, 1, 'W', '', '{}', '[]', ?)",
        (DEFINITION, NOW),
    )
    db.execute(
        "INSERT INTO workflow_runs (id, definition_id, definition_version, name, description, status, attempt, metadata, created_at, updated_at, version) "
        "VALUES (?, ?, 1, 'W', '', 'waiting_approval', 1, '{}', ?, ?, 4)",
        (RUN, DEFINITION, NOW, NOW),
    )
    db.executemany(
        "INSERT INTO workflow_run_steps (run_id, task_id, position, name, action, configuration, dependencies, status, created_at, metadata, approval_id) "
        "VALUES (?, ?, ?, ?, 'tool', '{}', '[]', ?, ?, '{}', ?)",
        [(RUN, "one", 0, "One", "completed", NOW, None), (RUN, "two", 1, "Two", "waiting_approval", NOW, STEP_APPROVAL)],
    )
    columns = "id, state, caller, subject, tool_name, tool_version, tool_contract, arguments, operation_digest, reason, created_at, expires_at, version"
    db.executemany(
        f"INSERT INTO approvals ({columns}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
        [
            _approval(AGENT_APPROVAL, "agent", f'{{"agent_id": "{AGENT}", "execution_id": "{EXECUTION_DASHED}"}}', "4" * 64, "pending"),
            _approval(STEP_APPROVAL, "workflow", f'{{"workflow_id": "{RUN_DASHED}", "workflow_task_id": "two", "workflow_attempt": "1"}}', "5" * 64, "approved"),
            _approval(OPERATOR_APPROVAL, "operator", "{}", "6" * 64, "rejected"),
        ],
    )
    db.commit()
    db.close()


def _snapshot(path: Path) -> dict[str, list[tuple[object, ...]]]:
    """Every existing table's rows (approvals without the two columns 0006 adds)."""
    db = sqlite3.connect(path)
    try:
        snapshot = {}
        for table in EXISTING:
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})") if row[1] not in {"execution_id", "workflow_id"} or table != "approvals"]
            snapshot[table] = sorted(db.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall(), key=repr)
        return snapshot
    finally:
        db.close()


def _query(path: Path, sql: str) -> list[tuple[object, ...]]:
    db = sqlite3.connect(path)
    try:
        return db.execute(sql).fetchall()
    finally:
        db.close()


def test_history_migration_keeps_every_existing_row_and_backfills_approval_links(tmp_path: Path) -> None:
    path = tmp_path / "migrate.db"
    config = alembic_config(f"sqlite+aiosqlite:///{path}")
    config.attributes["configure_logging"] = False
    command.upgrade(config, "0005")
    _seed(path)
    before = _snapshot(path)
    assert {table: len(rows) for table, rows in before.items()} == {
        "agents": 1, "agent_sessions": 1, "agent_session_messages": 2, "agent_memories": 1, "executions": 1,
        "execution_transitions": 3, "workflow_definitions": 1, "workflow_runs": 1,
        "workflow_run_steps": 2, "approvals": 3,
    }

    command.upgrade(config, "0006")
    assert _snapshot(path) == before
    assert _query(path, "PRAGMA foreign_key_check") == []
    assert sorted(_query(path, "SELECT id, execution_id, workflow_id FROM approvals")) == [
        (AGENT_APPROVAL, EXECUTION, None),  # stored in the application's UUID format
        (STEP_APPROVAL, None, RUN),
        (OPERATOR_APPROVAL, None, None),
    ]
    for table in NEW:
        assert _query(path, f"SELECT COUNT(*) FROM {table}") == [(0,)]
    assert _query(path, "SELECT COUNT(*) FROM sqlite_master WHERE name = 'uq_approvals_active_operation'") == [(1,)]

    command.downgrade(config, "0005")
    assert _snapshot(path) == before
    assert _query(path, "PRAGMA foreign_key_check") == []
    assert [row[1] for row in _query(path, "PRAGMA table_info(approvals)") if row[1] in {"execution_id", "workflow_id"}] == []
    assert _query(path, f"SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN {NEW!r}") == [(0,)]
    assert _query(path, "SELECT COUNT(*) FROM sqlite_master WHERE name = 'uq_approvals_active_operation'") == [(1,)]

    command.upgrade(config, "head")
    assert _snapshot(path) == before
    assert _query(path, "PRAGMA foreign_key_check") == []
    assert len(_query(path, "SELECT id FROM approvals WHERE execution_id IS NOT NULL OR workflow_id IS NOT NULL")) == 2
