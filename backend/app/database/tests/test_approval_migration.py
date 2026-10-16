"""Migration 0005 keeps every existing row, including child rows on SQLite.

SQLite applies a constraint change by recreating the table. With foreign keys enforced,
dropping a parent table cascade-deletes its children, which once wiped execution
timelines and workflow steps. This test seeds parents and children at 0004 and checks
that nothing is lost through upgrade, downgrade and upgrade again.
"""

import sqlite3
from pathlib import Path

from alembic import command

from backend.app.database.migrations import alembic_config

AGENT, EXECUTION, RUN = "a" * 32, "e" * 32, "f" * 32
NOW = "2026-10-16 10:00:00.000000"


def _seed(path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO agents (id, name, description, type, status, tags, metadata, allowed_tools, instructions, created_at, updated_at, version) "
        "VALUES (?, 'A', 'd', 't', 'idle', '[]', '{}', '[]', '', ?, ?, 1)",
        (AGENT, NOW, NOW),
    )
    db.execute(
        "INSERT INTO executions (id, agent_id, status, attempt, metadata, created_at, updated_at, version) VALUES (?, ?, 'completed', 1, '{}', ?, ?, 1)",
        (EXECUTION, AGENT, NOW, NOW),
    )
    db.executemany(
        "INSERT INTO execution_transitions (execution_id, sequence, from_status, to_status, at) VALUES (?, ?, ?, ?, ?)",
        [(EXECUTION, 1, None, "pending", NOW), (EXECUTION, 2, "pending", "completed", NOW)],
    )
    db.execute(
        "INSERT INTO workflow_runs (id, name, description, status, attempt, metadata, created_at, updated_at, version) VALUES (?, 'W', '', 'completed', 1, '{}', ?, ?, 1)",
        (RUN, NOW, NOW),
    )
    db.executemany(
        "INSERT INTO workflow_run_steps (run_id, task_id, position, name, action, configuration, dependencies, status, created_at, metadata) "
        "VALUES (?, ?, ?, ?, 'tool', '{}', '[]', 'completed', ?, '{}')",
        [(RUN, "one", 0, "One", NOW), (RUN, "two", 1, "Two", NOW)],
    )
    db.commit()
    db.close()


def _counts(path: Path) -> dict[str, int]:
    db = sqlite3.connect(path)
    try:
        return {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("agents", "executions", "execution_transitions", "workflow_runs", "workflow_run_steps")}
    finally:
        db.close()


def _foreign_key_problems(path: Path) -> int:
    db = sqlite3.connect(path)
    try:
        return len(db.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        db.close()


def test_upgrade_and_downgrade_keep_child_rows_on_sqlite(tmp_path: Path) -> None:
    path = tmp_path / "migrate.db"
    config = alembic_config(f"sqlite+aiosqlite:///{path}")
    config.attributes["configure_logging"] = False
    command.upgrade(config, "0004")
    _seed(path)
    seeded = _counts(path)
    assert seeded == {"agents": 1, "executions": 1, "execution_transitions": 2, "workflow_runs": 1, "workflow_run_steps": 2}

    command.upgrade(config, "0005")
    assert _counts(path) == seeded and _foreign_key_problems(path) == 0
    command.downgrade(config, "0004")
    assert _counts(path) == seeded and _foreign_key_problems(path) == 0
    command.upgrade(config, "head")
    assert _counts(path) == seeded and _foreign_key_problems(path) == 0
