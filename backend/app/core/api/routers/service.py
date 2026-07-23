"""Service-level API endpoints."""

from fastapi import APIRouter

from backend.app.core.core_services.config.settings import settings


router = APIRouter(tags=["service"])


@router.get("/")
async def root() -> dict[str, str]:
    """Return basic service metadata."""
    return {
        "application": settings.APP_NAME,
        "status": "running",
        "version": settings.APP_VERSION,
    }


@router.get("/health")
async def health() -> dict[str, str]:
    """Report service liveness."""
    return {"status": "ok"}
