"""Unit tests for the Genesis Tool Manager."""

import pytest

from backend.app.core.tool_manager.application.tool_manager import ToolManager
from backend.app.core.tool_manager.domain.exceptions import (
    DuplicateToolError,
    ToolNotFoundError,
)
from backend.app.core.tool_manager.domain.tool import Tool


class EchoTool(Tool):
    """Test tool that returns a supplied value."""

    @property
    def name(self) -> str:
        """Return the test tool name."""
        return "echo"

    async def execute(self, **arguments: object) -> object:
        """Return the value supplied to the tool."""
        return arguments["value"]


class FailingTool(Tool):
    """Test tool that raises during execution."""

    @property
    def name(self) -> str:
        """Return the failing test tool name."""
        return "failing"

    async def execute(self, **arguments: object) -> object:
        """Raise the expected execution failure."""
        raise RuntimeError("tool execution failed")


def test_register_and_resolve_tool() -> None:
    """A registered tool can be resolved by name."""
    manager = ToolManager()
    tool = EchoTool()
    manager.register(tool)

    assert manager.resolve("echo") is tool


def test_duplicate_registration_raises_exception() -> None:
    """Tools cannot share a registry name."""
    manager = ToolManager()
    manager.register(EchoTool())

    with pytest.raises(DuplicateToolError, match="echo"):
        manager.register(EchoTool())


def test_unknown_tool_resolution_raises_exception() -> None:
    """Unknown names produce a meaningful resolution error."""
    with pytest.raises(ToolNotFoundError, match="missing"):
        ToolManager().resolve("missing")


@pytest.mark.asyncio
async def test_execute_registered_tool() -> None:
    """Tool execution forwards named arguments to the resolved tool."""
    manager = ToolManager()
    manager.register(EchoTool())

    assert await manager.execute("echo", value="Genesis") == "Genesis"


def test_unregister_tool_removes_registration() -> None:
    """Unregistering returns the tool and removes its name binding."""
    manager = ToolManager()
    tool = EchoTool()
    manager.register(tool)

    assert manager.unregister("echo") is tool
    with pytest.raises(ToolNotFoundError):
        manager.resolve("echo")


def test_multiple_tools_can_be_registered() -> None:
    """Distinct tool names coexist in the same manager."""
    manager = ToolManager()
    echo_tool = EchoTool()
    failing_tool = FailingTool()
    manager.register(echo_tool)
    manager.register(failing_tool)

    assert manager.resolve("echo") is echo_tool
    assert manager.resolve("failing") is failing_tool


@pytest.mark.asyncio
async def test_execution_errors_propagate() -> None:
    """Tool execution failures are visible to the caller."""
    manager = ToolManager()
    manager.register(FailingTool())

    with pytest.raises(RuntimeError, match="tool execution failed"):
        await manager.execute("failing")
