"""Alembic environment for Genesis Core tables (async engine, DATABASE_URL-driven)."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

# Importing the ORM modules registers their tables on Base.metadata.
from backend.app.core.agent_runtime.infrastructure import orm as _agent_orm  # noqa: F401
from backend.app.core.execution_runtime.infrastructure import orm as _execution_orm  # noqa: F401
from backend.app.core.workflow_runtime.infrastructure import orm as _workflow_orm  # noqa: F401
from backend.app.core.core_services.config.settings import settings
from backend.app.database.base import Base
from backend.app.database.engine import create_database_engine


config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return config.attributes.get("database_url") or settings.DATABASE_URL


def run_migrations_offline() -> None:
    """Emit SQL for review (``alembic upgrade head --sql``) without connecting."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    # Batch mode lets future ALTERs work on SQLite, which cannot alter most constraints.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_database_engine(_database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync)
            await connection.commit()
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
