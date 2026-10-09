"""Database fixtures for persistence adapter tests.

Tests run against the per-test SQLite database from ``backend/conftest.py``. Setting
``GENESIS_TEST_POSTGRES_URL`` (a disposable database — it is reset for every test)
additionally runs them against PostgreSQL.
"""

import os
from collections.abc import AsyncIterator

import pytest
from alembic import command
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.database import create_database_engine, create_session_factory
from backend.app.database.migrations import alembic_config


POSTGRES_URL = os.environ.get("GENESIS_TEST_POSTGRES_URL")
BACKENDS = ["sqlite", *(["postgresql"] if POSTGRES_URL else [])]


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
