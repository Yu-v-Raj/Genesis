"""Application service for registering and invoking Genesis Core tools."""

from threading import RLock

from backend.app.core.tool_manager.domain.exceptions import (
    DuplicateToolError,
    InvalidToolNameError,
    ToolNotFoundError,
)
from backend.app.core.tool_manager.domain.tool import Tool


class ToolManager:
    """Maintain an in-memory registry of named asynchronous tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._lock = RLock()

    def register(self, tool: Tool) -> None:
        """Register a tool under its unique name."""
        if not isinstance(tool, Tool):
            raise TypeError("Registered tools must implement the Tool base class.")
        self._validate_tool_name(tool.name)

        with self._lock:
            if tool.name in self._tools:
                raise DuplicateToolError(tool.name)
            self._tools[tool.name] = tool

    def unregister(self, tool_name: str) -> Tool:
        """Remove and return a registered tool."""
        self._validate_tool_name(tool_name)
        with self._lock:
            try:
                return self._tools.pop(tool_name)
            except KeyError as error:
                raise ToolNotFoundError(tool_name) from error

    def resolve(self, tool_name: str) -> Tool:
        """Return the tool registered under ``tool_name``."""
        self._validate_tool_name(tool_name)
        with self._lock:
            try:
                return self._tools[tool_name]
            except KeyError as error:
                raise ToolNotFoundError(tool_name) from error

    async def execute(self, tool_name: str, **arguments: object) -> object:
        """Resolve and asynchronously execute a registered tool."""
        tool = self.resolve(tool_name)
        return await tool.execute(**arguments)

    def registered_names(self) -> tuple[str, ...]:
        """Return a snapshot of registered tool names."""
        with self._lock:
            return tuple(self._tools)

    @staticmethod
    def _validate_tool_name(tool_name: object) -> None:
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise InvalidToolNameError("Tool names must be non-empty strings.")
