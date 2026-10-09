"""Async SQLAlchemy engine construction for backend persistence adapters."""

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_database_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Create an engine for ``url``; the caller owns it and must dispose it on shutdown."""
    if make_url(url).get_backend_name() == "sqlite":
        engine = create_async_engine(url, echo=echo)
        # SQLite only enforces foreign keys (and ON DELETE CASCADE) when asked per connection.
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
        return engine
    return create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
    )


def redacted_url(url: str) -> str:
    """Render a database URL for messages and logs without its password."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "<invalid DATABASE_URL>"


def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
