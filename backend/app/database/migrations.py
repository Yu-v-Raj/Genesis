"""Programmatic access to the Alembic migration history and startup schema checks."""

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.app.core.core_services.config.constants import PROJECT_ROOT


ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


class DatabaseStartupError(RuntimeError):
    """Raised when the configured database cannot be used; the message is safe to print."""


def alembic_config(database_url: str | None = None) -> Config:
    """Load ``alembic.ini``; an explicit URL overrides ``DATABASE_URL`` for this run."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(PROJECT_ROOT / "infra" / "migrations"))
    if database_url is not None:
        # Passed as an attribute, not a main option, so '%' in passwords needs no escaping.
        config.attributes["database_url"] = database_url
    return config


def upgrade_to_head(database_url: str) -> None:
    """Apply every pending migration. Must not be called from a running event loop."""
    command.upgrade(alembic_config(database_url), "head")


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


async def verify_database(engine: AsyncEngine) -> None:
    """Fail fast, with an actionable message, if the database is unreachable or not migrated."""
    location = engine.url.render_as_string(hide_password=True)
    try:
        async with engine.connect() as connection:
            current = await connection.run_sync(
                lambda sync: MigrationContext.configure(sync).get_current_revision()
            )
    except Exception as error:
        raise DatabaseStartupError(
            f"Cannot connect to the Genesis database at {location} ({type(error).__name__}). "
            "Check that the database server is running and DATABASE_URL is correct."
        ) from error
    expected = head_revision()
    if current != expected:
        raise DatabaseStartupError(
            f"The Genesis database at {location} is at migration {current or 'none'}, "
            f"but this code requires {expected}. Run: alembic upgrade head"
        )
