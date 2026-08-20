"""FastAPI dependencies for read-only Genesis system state."""

from typing import cast

from fastapi import Depends
from starlette.requests import HTTPConnection

from backend.app.core.core_services.service_registry import ServiceRegistry
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.execution_runtime.application.execution_manager import ExecutionManager
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.observability.infrastructure.event_history import EventHistory
from backend.app.core.plugin_system.application.plugin_manager import PluginManager
from backend.app.core.realtime.application.websocket_manager import WebSocketManager
from backend.app.core.runtime.application.lifecycle_manager import RuntimeLifecycleManager
from backend.app.core.tool_manager.application.tool_manager import ToolManager
from backend.app.core.workflow_engine.application.workflow_engine import WorkflowEngine


def get_service_registry(connection: HTTPConnection) -> ServiceRegistry:
    """Return the app-scoped Core service registry."""
    return cast(ServiceRegistry, connection.app.state.service_registry)


def get_runtime_manager(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> RuntimeLifecycleManager:
    """Resolve the app-scoped runtime lifecycle manager."""
    return registry.resolve(RuntimeLifecycleManager)


def get_event_history(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> EventHistory:
    """Resolve the app-scoped in-memory event history."""
    return registry.resolve(EventHistory)


def get_websocket_manager(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> WebSocketManager:
    """Resolve the app-scoped WebSocket connection manager."""
    return registry.resolve(WebSocketManager)


def get_agent_registry(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> AgentRegistry:
    """Resolve the app-scoped Agent Runtime registry."""
    return registry.resolve(AgentRegistry)


def get_agent_manager(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> AgentManager:
    """Resolve the app-scoped Agent Runtime lifecycle manager."""
    return registry.resolve(AgentManager)


def get_execution_manager(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> ExecutionManager:
    """Resolve the app-scoped Execution Runtime lifecycle manager."""
    return registry.resolve(ExecutionManager)


def get_tool_runtime_manager(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> ToolRuntimeManager:
    """Resolve the app-scoped Tool Runtime manager."""
    return registry.resolve(ToolRuntimeManager)


def get_tool_manager(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> ToolManager:
    """Resolve the app-scoped Tool Manager."""
    return registry.resolve(ToolManager)


def get_plugin_manager(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> PluginManager:
    """Resolve the app-scoped Plugin Manager."""
    return registry.resolve(PluginManager)


def get_memory_manager(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> MemoryManager:
    """Resolve the app-scoped Memory Manager."""
    return registry.resolve(MemoryManager)


def get_workflow_engine(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> WorkflowEngine:
    """Resolve the app-scoped Workflow Engine."""
    return registry.resolve(WorkflowEngine)
