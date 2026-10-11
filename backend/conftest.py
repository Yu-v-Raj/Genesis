"""Test-wide database isolation.

Every test runs against its own freshly migrated SQLite file, so tests never touch the
developer's real database (DATABASE_URL in .env) and never see each other's data. The
schema is produced by the real Alembic migrations once per run, then copied per test.

Persistence tests that use the ``database_url`` / ``session_factory`` fixtures also run
against PostgreSQL when ``GENESIS_TEST_POSTGRES_URL`` names a *disposable* database (it
is reset for every such test).
"""

import os
import shutil
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.core_services.config.settings import settings
from backend.app.database import create_database_engine, create_session_factory
from backend.app.database.migrations import alembic_config, upgrade_to_head


POSTGRES_URL = os.environ.get("GENESIS_TEST_POSTGRES_URL")
BACKENDS = ["sqlite", *(["postgresql"] if POSTGRES_URL else [])]


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


@pytest.fixture(params=BACKENDS)
def database_url(request: pytest.FixtureRequest, isolated_database: str) -> str:
    if request.param == "sqlite":
        return isolated_database
    assert POSTGRES_URL is not None
    config = alembic_config(POSTGRES_URL)
    config.attributes["configure_logging"] = False
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return POSTGRES_URL


@pytest.fixture
async def session_factory(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_database_engine(database_url)
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()
