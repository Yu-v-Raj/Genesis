"""Async session factory construction."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a factory for short-lived sessions; each repository call owns one transaction."""
    return async_sessionmaker(engine, expire_on_commit=False)
