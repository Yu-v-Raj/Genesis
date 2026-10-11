"""One short transaction per repository call, with storage errors made safe to show."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.core_services.logging.logger import logger
from backend.app.core.core_services.persistence import PersistenceError


STORAGE_UNAVAILABLE = "Genesis storage is unavailable. Try again shortly."


@asynccontextmanager
async def persistence_transaction(
    factory: async_sessionmaker[AsyncSession], operation: str
) -> AsyncIterator[AsyncSession]:
    """Commit on success, roll back on any error.

    SQLAlchemy errors, and connection failures that drivers raise as plain ``OSError`` or
    ``TimeoutError``, become ``PersistenceError`` without the URL, credentials, or data.
    Domain errors raised inside the block pass through unchanged (after rollback).
    """
    try:
        async with factory() as session, session.begin():
            yield session
    except (SQLAlchemyError, OSError, TimeoutError) as error:
        logger.error(
            "Persistence operation failed",
            extra={"genesis_context": {"operation": operation, "error_type": type(error).__name__}},
        )
        raise PersistenceError(STORAGE_UNAVAILABLE) from error
