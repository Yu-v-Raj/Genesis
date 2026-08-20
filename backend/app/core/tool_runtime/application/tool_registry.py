"""Thread-safe Tool registry with typed registration events."""

from threading import RLock

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import ToolRegistered
from backend.app.core.tool_runtime.domain.exceptions import (
    DuplicateToolError,
    ToolDisabledError,
    ToolNotFoundError,
)
from backend.app.core.tool_runtime.domain.tool import Tool


class ToolRegistry:
    """Store immutable Tool declarations and resolve enabled implementations."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._tools: dict[str, Tool] = {}
        self._lock = RLock()

    async def register(self, tool: Tool) -> Tool:
        """Register a Tool and publish its registration."""
        with self._lock:
            if tool.name in self._tools:
                raise DuplicateToolError(tool.name)
            self._tools[tool.name] = tool
        await self._event_bus.publish(
            ToolRegistered(source="tool_registry", payload={"tool_name": tool.name})
        )
        return tool

    def unregister(self, tool_name: str) -> Tool:
        """Remove and return a registered Tool."""
        with self._lock:
            try:
                return self._tools.pop(tool_name)
            except KeyError as error:
                raise ToolNotFoundError(tool_name) from error

    def get(self, tool_name: str) -> Tool:
        """Resolve one registered Tool without checking availability."""
        with self._lock:
            try:
                return self._tools[tool_name]
            except KeyError as error:
                raise ToolNotFoundError(tool_name) from error

    def resolve_enabled(self, tool_name: str) -> Tool:
        """Resolve a Tool and enforce its enabled state."""
        tool = self.get(tool_name)
        if not tool.definition.enabled:
            raise ToolDisabledError(tool_name)
        return tool

    def list(self) -> tuple[Tool, ...]:
        """Return Tools in deterministic registration order."""
        with self._lock:
            return tuple(self._tools.values())
