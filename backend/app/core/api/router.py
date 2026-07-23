"""Aggregate router for Genesis API endpoints."""

from fastapi import APIRouter

from backend.app.core.api.routers.service import router as service_router
from backend.app.core.api.routers.system import router as system_router


api_router = APIRouter()
api_router.include_router(service_router)
api_router.include_router(system_router)
