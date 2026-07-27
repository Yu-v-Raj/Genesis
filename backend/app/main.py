"""Genesis ASGI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.api.router import api_router
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.core_services.config.settings import settings
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.service_registry import ServiceRegistry
from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.observability.application.heartbeat import HeartbeatService
from backend.app.core.observability.application.logger_service import LoggerService
from backend.app.core.observability.domain.events import (
    ServiceRegistered,
    SystemStarted,
    SystemStopped,
)
from backend.app.core.observability.infrastructure.event_history import EventHistory
from backend.app.core.plugin_system.application.plugin_manager import PluginManager
from backend.app.core.realtime.application.gateway import RealtimeGateway
from backend.app.core.realtime.application.websocket_manager import WebSocketManager
from backend.app.core.runtime.application.lifecycle_manager import RuntimeLifecycleManager
from backend.app.core.tool_manager.application.tool_manager import ToolManager
from backend.app.core.workflow_engine.application.workflow_engine import WorkflowEngine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle resources."""
    service_registry = ServiceRegistry()
    event_bus = EventBus()
    event_history = EventHistory(settings.EVENT_HISTORY_SIZE)
    websocket_manager = WebSocketManager()
    realtime_gateway = RealtimeGateway(websocket_manager)
    agent_registry = AgentRegistry(event_bus)
    tool_manager = ToolManager()
    plugin_manager = PluginManager()
    memory_manager = MemoryManager()
    workflow_engine = WorkflowEngine(event_bus)
    runtime_manager = RuntimeLifecycleManager(service_registry)
    started_at = monotonic()
    logger_service = LoggerService(event_bus)
    heartbeat_service = HeartbeatService(
        event_bus,
        runtime_state=lambda: runtime_manager.state.value,
        uptime=lambda: max(0.0, monotonic() - started_at),
        interval_seconds=settings.HEARTBEAT_INTERVAL_SECONDS,
    )

    event_bus.subscribe(event_history.record)
    event_bus.subscribe(realtime_gateway.broadcast_event)
    service_registry.register_singleton(EventBus, event_bus)
    service_registry.register_singleton(EventHistory, event_history)
    service_registry.register_singleton(WebSocketManager, websocket_manager)
    service_registry.register_singleton(RealtimeGateway, realtime_gateway)
    service_registry.register_singleton(AgentRegistry, agent_registry)
    service_registry.register_singleton(LoggerService, logger_service)
    service_registry.register_singleton(ToolManager, tool_manager)
    service_registry.register_singleton(PluginManager, plugin_manager)
    service_registry.register_singleton(MemoryManager, memory_manager)
    service_registry.register_singleton(WorkflowEngine, workflow_engine)
    service_registry.register_singleton(RuntimeLifecycleManager, runtime_manager)
    service_registry.register_singleton(HeartbeatService, heartbeat_service)
    app.state.service_registry = service_registry
    app.state.started_at = started_at

    for service_name in (
        "EventBus",
        "EventHistory",
        "WebSocketManager",
        "RealtimeGateway",
        "AgentRegistry",
        "LoggerService",
        "ToolManager",
        "PluginManager",
        "MemoryManager",
        "WorkflowEngine",
        "RuntimeLifecycleManager",
        "HeartbeatService",
    ):
        await event_bus.publish(
            ServiceRegistered(source="bootstrap", payload={"service": service_name})
        )

    await runtime_manager.startup()
    await event_bus.publish(SystemStarted(source="runtime"))
    await logger_service.info("Genesis application startup", source="runtime")
    await heartbeat_service.start()
    try:
        yield
    finally:
        await heartbeat_service.stop()
        await runtime_manager.shutdown()
        await event_bus.publish(SystemStopped(source="runtime"))
        await logger_service.info("Genesis application shutdown", source="runtime")


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Allow the Next.js frontend to communicate with the backend during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
