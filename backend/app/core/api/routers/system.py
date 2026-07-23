"""Read-only API routes exposing current Genesis system state."""

from time import monotonic

from fastapi import APIRouter, Depends, Request

from backend.app.core.api.dependencies.system import (
    get_memory_manager,
    get_plugin_manager,
    get_runtime_manager,
    get_service_registry,
    get_tool_manager,
    get_workflow_engine,
)
from backend.app.core.api.schemas.system import (
    SystemHealthResponse,
    SystemMemoryResponse,
    SystemPluginsResponse,
    SystemRuntimeResponse,
    SystemServicesResponse,
    SystemToolsResponse,
    SystemWorkflowsResponse,
)
from backend.app.core.core_services.service_registry import ServiceKey, ServiceRegistry
from backend.app.core.core_services.config.settings import settings
from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.plugin_system.application.plugin_manager import PluginManager
from backend.app.core.runtime.application.lifecycle_manager import RuntimeLifecycleManager
from backend.app.core.tool_manager.application.tool_manager import ToolManager
from backend.app.core.workflow_engine.application.workflow_engine import WorkflowEngine


router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health", response_model=SystemHealthResponse)
async def system_health(request: Request, runtime: RuntimeLifecycleManager = Depends(get_runtime_manager)) -> SystemHealthResponse:
    """Return current Genesis process health and uptime."""
    uptime = max(0.0, monotonic() - request.app.state.started_at)
    return SystemHealthResponse(
        status=runtime.state.value,
        version=settings.APP_VERSION,
        uptime=uptime,
    )


@router.get("/runtime", response_model=SystemRuntimeResponse)
async def system_runtime(
    runtime: RuntimeLifecycleManager = Depends(get_runtime_manager),
) -> SystemRuntimeResponse:
    """Return the current runtime lifecycle state."""
    return SystemRuntimeResponse(state=runtime.state.value)


@router.get("/services", response_model=SystemServicesResponse)
async def system_services(
    registry: ServiceRegistry = Depends(get_service_registry),
) -> SystemServicesResponse:
    """Return the Core services registered for this application instance."""
    return SystemServicesResponse(services=[_service_key_name(key) for key in registry.registered_keys()])


@router.get("/tools", response_model=SystemToolsResponse)
async def system_tools(
    tool_manager: ToolManager = Depends(get_tool_manager),
) -> SystemToolsResponse:
    """Return names of currently registered tools."""
    return SystemToolsResponse(tools=list(tool_manager.registered_names()))


@router.get("/plugins", response_model=SystemPluginsResponse)
async def system_plugins(
    plugin_manager: PluginManager = Depends(get_plugin_manager),
) -> SystemPluginsResponse:
    """Return names of currently registered plugins."""
    return SystemPluginsResponse(plugins=list(plugin_manager.registered_names()))


@router.get("/memory", response_model=SystemMemoryResponse)
async def system_memory(
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> SystemMemoryResponse:
    """Return names of currently registered memory providers."""
    return SystemMemoryResponse(providers=list(await memory_manager.registered_names()))


@router.get("/workflows", response_model=SystemWorkflowsResponse)
async def system_workflows(
    workflow_engine: WorkflowEngine = Depends(get_workflow_engine),
) -> SystemWorkflowsResponse:
    """Return names of currently registered workflows."""
    return SystemWorkflowsResponse(workflows=list(await workflow_engine.registered_names()))


def _service_key_name(key: ServiceKey) -> str:
    """Format a service registry key for an external read-only response."""
    return key if isinstance(key, str) else key.__name__
