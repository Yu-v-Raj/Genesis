"""Genesis ASGI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.core.api.router import api_router
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_interaction_service import AgentInteractionService
from backend.app.core.agent_runtime.application.agent_configuration_service import AgentConfigurationService
from backend.app.core.agent_runtime.infrastructure.sqlalchemy_repositories import (
    SqlAlchemyAgentRepository,
    SqlAlchemySessionRepository,
)
from backend.app.core.core_services.config.settings import settings
from backend.app.core.core_services.logging.logger import logger
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.service_registry import ServiceRegistry
from backend.app.core.execution_runtime.application.execution_executor import ExecutionExecutor
from backend.app.core.execution_runtime.application.execution_manager import ExecutionManager, default_worker_id
from backend.app.core.execution_runtime.application.repositories import ExecutionRepository
from backend.app.core.execution_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyExecutionRepository
from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.memory.infrastructure.in_memory_provider import InMemoryProvider
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
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.tool import builtin_tools
from backend.app.core.workflow_engine.application.workflow_engine import WorkflowEngine
from backend.app.core.workflow_runtime.application.repositories import WorkflowRepository
from backend.app.core.workflow_runtime.application.workflow_manager import WorkflowManager
from backend.app.core.workflow_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyWorkflowRepository
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.infrastructure.openai_provider import OpenAIProvider
from backend.app.core.llm_runtime.infrastructure.gemini_provider import GeminiProvider
from backend.app.database import create_database_engine, create_session_factory
from backend.app.database.migrations import DatabaseStartupError, verify_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle resources."""
    database_engine = create_database_engine(settings.DATABASE_URL)
    try:
        await verify_database(database_engine)
    except DatabaseStartupError as error:
        await database_engine.dispose()
        logger.error(str(error))
        raise
    session_factory = create_session_factory(database_engine)
    service_registry = ServiceRegistry()
    event_bus = EventBus()
    event_history = EventHistory(settings.EVENT_HISTORY_SIZE)
    websocket_manager = WebSocketManager()
    realtime_gateway = RealtimeGateway(websocket_manager)
    agent_registry = AgentRegistry(event_bus, SqlAlchemyAgentRepository(session_factory))
    agent_manager = AgentManager(
        agent_registry, event_bus, SqlAlchemySessionRepository(session_factory)
    )
    worker_id = default_worker_id()
    execution_repository = SqlAlchemyExecutionRepository(session_factory)
    execution_executor = ExecutionExecutor()
    execution_manager = ExecutionManager(
        agent_registry,
        execution_executor,
        execution_repository,
        event_bus,
        worker_id=worker_id,
        lease_seconds=settings.WORKER_LEASE_SECONDS,
        concurrency=settings.WORKER_CONCURRENCY,
    )
    tool_manager = ToolManager()
    tool_registry = ToolRegistry(event_bus)
    tool_executor = ToolExecutor(tool_registry, event_bus)
    tool_runtime_manager = ToolRuntimeManager(tool_registry, tool_executor, event_bus)
    for tool in builtin_tools():
        await tool_runtime_manager.register(tool)
    execution_executor.set_tool_manager(tool_runtime_manager)
    plugin_manager = PluginManager()
    memory_provider = InMemoryProvider()
    memory_manager = MemoryManager(memory_provider, event_bus)
    workflow_engine = WorkflowEngine(event_bus)
    workflow_repository = SqlAlchemyWorkflowRepository(session_factory)
    workflow_manager = WorkflowManager(
        tool_runtime_manager,
        event_bus,
        repository=workflow_repository,
        worker_id=worker_id,
        lease_seconds=settings.WORKER_LEASE_SECONDS,
        concurrency=settings.WORKER_CONCURRENCY,
    )
    llm_provider_registry = LLMProviderRegistry()
    llm_provider_registry.register(OpenAIProvider(settings))
    llm_provider_registry.register(GeminiProvider(settings))
    llm_manager = LLMManager(llm_provider_registry, event_bus)
    agent_interaction_service = AgentInteractionService(
        agent_registry, agent_manager, llm_manager, tool_manager=tool_runtime_manager
    )
    agent_configuration_service = AgentConfigurationService(
        agent_registry, agent_manager, llm_manager, tool_runtime_manager
    )
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
    service_registry.register_singleton(AgentManager, agent_manager)
    service_registry.register_singleton(AgentInteractionService, agent_interaction_service)
    service_registry.register_singleton(AgentConfigurationService, agent_configuration_service)
    service_registry.register_singleton(ExecutionRepository, execution_repository)
    service_registry.register_singleton(ExecutionExecutor, execution_executor)
    service_registry.register_singleton(ExecutionManager, execution_manager)
    service_registry.register_singleton(LoggerService, logger_service)
    service_registry.register_singleton(ToolManager, tool_manager)
    service_registry.register_singleton(ToolRegistry, tool_registry)
    service_registry.register_singleton(ToolExecutor, tool_executor)
    service_registry.register_singleton(ToolRuntimeManager, tool_runtime_manager)
    service_registry.register_singleton(PluginManager, plugin_manager)
    service_registry.register_singleton(MemoryManager, memory_manager)
    service_registry.register_singleton(InMemoryProvider, memory_provider)
    service_registry.register_singleton(WorkflowEngine, workflow_engine)
    service_registry.register_singleton(WorkflowRepository, workflow_repository)
    service_registry.register_singleton(WorkflowManager, workflow_manager)
    service_registry.register_singleton(LLMProviderRegistry, llm_provider_registry)
    service_registry.register_singleton(LLMManager, llm_manager)
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
        "AgentManager",
        "AgentInteractionService",
        "AgentConfigurationService",
        "ExecutionRepository",
        "ExecutionExecutor",
        "ExecutionManager",
        "LoggerService",
        "ToolManager",
        "ToolRegistry",
        "ToolExecutor",
        "ToolRuntimeManager",
        "PluginManager",
        "MemoryManager",
        "InMemoryProvider",
        "WorkflowEngine",
        "WorkflowRepository",
        "WorkflowManager",
        "LLMProviderRegistry",
        "LLMManager",
        "RuntimeLifecycleManager",
        "HeartbeatService",
    ):
        await event_bus.publish(
            ServiceRegistered(source="bootstrap", payload={"service": service_name})
        )

    await agent_manager.restore_agents()
    # Resolve work left by a previous process, then start claiming queued work.
    await execution_manager.start()
    await workflow_manager.start_worker()
    await runtime_manager.startup()
    await event_bus.publish(SystemStarted(source="runtime"))
    await logger_service.info("Genesis application startup", source="runtime")
    await heartbeat_service.start()
    try:
        yield
    finally:
        await execution_manager.shutdown()
        await workflow_manager.shutdown()
        await heartbeat_service.stop()
        await runtime_manager.shutdown()
        await event_bus.publish(SystemStopped(source="runtime"))
        await logger_service.info("Genesis application shutdown", source="runtime")
        await database_engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Allow the Next.js frontend to communicate with the backend during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(PersistenceConflictError)
async def persistence_conflict_handler(_: Request, error: PersistenceConflictError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(error)})


@app.exception_handler(PersistenceError)
async def persistence_error_handler(_: Request, error: PersistenceError) -> JSONResponse:
    """Storage failures become a retryable 503 whose message names no URL or credentials."""
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(error)})
