"""Genesis ASGI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI

from backend.app.core.api.router import api_router
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.service_registry import ServiceRegistry
from backend.app.core.core_services.config.settings import settings
from backend.app.core.core_services.logging.logger import logger
from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.plugin_system.application.plugin_manager import PluginManager
from backend.app.core.runtime.application.lifecycle_manager import RuntimeLifecycleManager
from backend.app.core.tool_manager.application.tool_manager import ToolManager
from backend.app.core.workflow_engine.application.workflow_engine import WorkflowEngine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle resources."""
    service_registry = ServiceRegistry()
    event_bus = EventBus()
    tool_manager = ToolManager()
    plugin_manager = PluginManager()
    memory_manager = MemoryManager()
    workflow_engine = WorkflowEngine(event_bus)
    runtime_manager = RuntimeLifecycleManager(service_registry)

    service_registry.register_singleton(EventBus, event_bus)
    service_registry.register_singleton(ToolManager, tool_manager)
    service_registry.register_singleton(PluginManager, plugin_manager)
    service_registry.register_singleton(MemoryManager, memory_manager)
    service_registry.register_singleton(WorkflowEngine, workflow_engine)
    service_registry.register_singleton(RuntimeLifecycleManager, runtime_manager)
    app.state.service_registry = service_registry
    app.state.started_at = monotonic()
    await runtime_manager.startup()
    logger.info("Genesis application startup")
    try:
        yield
    finally:
        await runtime_manager.shutdown()
        logger.info("Genesis application shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.include_router(api_router)
