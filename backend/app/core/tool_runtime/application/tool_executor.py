"""Framework-agnostic execution of Tool requests."""

from time import monotonic

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import ToolCompleted, ToolExecuted, ToolFailed
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.exceptions import ToolRuntimeError
from backend.app.core.tool_runtime.domain.tool_request import ToolRequest
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus


class ToolExecutor:
    """Resolve a request, invoke the Tool, and publish typed lifecycle events."""

    def __init__(self, registry: ToolRegistry, event_bus: EventBus) -> None:
        self._registry = registry
        self._event_bus = event_bus

    async def execute(self, request: ToolRequest) -> ToolResult:
        """Execute one ToolRequest and return a terminal ToolResult."""
        started = monotonic()
        await self._publish(ToolExecuted, request)
        try:
            result = await self._registry.resolve_enabled(request.tool_name).execute(request)
        except ToolRuntimeError as error:
            result = ToolResult(
                status=ToolResultStatus.FAILED,
                error=str(error),
                duration=monotonic() - started,
            )
        except Exception as error:
            result = ToolResult(
                status=ToolResultStatus.FAILED,
                error=str(error),
                duration=monotonic() - started,
            )
        if result.duration == 0:
            result = ToolResult(
                status=result.status,
                output=result.output,
                logs=result.logs,
                metadata=result.metadata,
                duration=monotonic() - started,
                error=result.error,
            )
        await self._publish(ToolCompleted if result.status is ToolResultStatus.COMPLETED else ToolFailed, request)
        return result

    async def _publish(self, event_type: type[ToolExecuted], request: ToolRequest) -> None:
        payload: dict[str, object] = {"tool_name": request.tool_name}
        if request.execution_id is not None:
            payload["execution_id"] = str(request.execution_id)
        if request.task_id is not None:
            payload["task_id"] = str(request.task_id)
        await self._event_bus.publish(event_type(source="tool_executor", payload=payload))
