"""Genesis ASGI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.core.core_services.config.settings import settings
from backend.app.core.core_services.logging.logger import logger


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle resources."""
    logger.info("Genesis application startup")
    yield
    logger.info("Genesis application shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


@app.get("/", tags=["service"])
async def root() -> dict[str, str]:
    """Return basic service metadata."""
    return {
        "application": settings.APP_NAME,
        "status": "running",
        "version": settings.APP_VERSION,
    }


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    """Report service liveness."""
    return {"status": "ok"}
