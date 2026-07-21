"""Async SQLAlchemy engine shared by backend persistence adapters."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.app.database.config import DATABASE_URL


engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)
