"""FastAPI dependencies for read-only Genesis system state."""

from typing import cast

from fastapi import Depends, Request

from backend.app.core.core_services.service_registry import ServiceRegistry
from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.plugin_system.application.plugin_manager import PluginManager
from backend.app.core.runtime.application.lifecycle_manager import RuntimeLifecycleManager
from backend.app.core.tool_manager.application.tool_manager import ToolManager
from backend.app.core.workflow_engine.application.workflow_engine import WorkflowEngine


def get_service_registry(request: Request) -> ServiceRegistry:
    """Return the app-scoped Core service registry."""
    return cast(ServiceRegistry, request.app.state.service_registry)


def get_runtime_manager(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> RuntimeLifecycleManager:
    """Resolve the app-scoped runtime lifecycle manager."""
    return registry.resolve(RuntimeLifecycleManager)


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
