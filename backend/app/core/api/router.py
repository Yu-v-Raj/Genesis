"""Aggregate router for Genesis API endpoints."""

from fastapi import APIRouter

from backend.app.core.api.routers.agents import router as agents_router
from backend.app.core.api.routers.executions import router as executions_router
from backend.app.core.api.routers.tools import router as tools_router
from backend.app.core.api.routers.observability import router as observability_router
from backend.app.core.api.routers.realtime import router as realtime_router
from backend.app.core.api.routers.service import router as service_router
from backend.app.core.api.routers.system import router as system_router


api_router = APIRouter()
api_router.include_router(agents_router)
api_router.include_router(executions_router)
api_router.include_router(tools_router)
api_router.include_router(observability_router)
api_router.include_router(realtime_router)
api_router.include_router(service_router)
api_router.include_router(system_router)
