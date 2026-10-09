"""Test-wide database isolation.

Every test runs against its own freshly migrated SQLite file, so tests never touch the
developer's real database (DATABASE_URL in .env) and never see each other's data. The
schema is produced by the real Alembic migrations once per run, then copied per test.
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.app.core.core_services.config.settings import settings
from backend.app.database.migrations import upgrade_to_head


def sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("db") / "template.db"
    upgrade_to_head(sqlite_url(path))
    return path


@pytest.fixture(autouse=True)
def isolated_database(
    migrated_template: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """Point the application at a private, migrated database for the duration of a test."""
    path = tmp_path / "genesis-test.db"
    shutil.copyfile(migrated_template, path)
    url = sqlite_url(path)
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    yield url
