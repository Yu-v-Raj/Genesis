"""Async session factory and FastAPI-compatible session dependency."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.database.engine import engine


async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one database session for a request or application operation."""
    async with async_session_factory() as session:
        yield session
