"""Unit tests for the Genesis Plugin Manager."""

import pytest

from backend.app.core.plugin_system.application.plugin_manager import PluginManager
from backend.app.core.plugin_system.domain.exceptions import (
    DuplicatePluginError,
    PluginNotFoundError,
)
from backend.app.core.plugin_system.domain.plugin import Plugin
from backend.app.core.tool_manager.application.tool_manager import ToolManager
from backend.app.core.tool_manager.domain.tool import Tool


class PluginTool(Tool):
    """Test tool registered by a test plugin."""

    @property
    def name(self) -> str:
        """Return the test tool name."""
        return "plugin_tool"

    async def execute(self, **arguments: object) -> object:
        """Return the value passed to the test tool."""
        return arguments["value"]


class ToolRegisteringPlugin(Plugin):
    """Test plugin that records lifecycle calls and registers one tool."""

    def __init__(self, events: list[str]) -> None:
        self._events = events

    @property
    def name(self) -> str:
        """Return the test plugin name."""
        return "example_plugin"

    async def initialize(self, tool_manager: ToolManager) -> None:
        """Register the test plugin's tool."""
        self._events.append("initialized")
        tool_manager.register(PluginTool())

    async def shutdown(self) -> None:
        """Record test plugin shutdown."""
        self._events.append("shutdown")


def test_register_and_resolve_plugin() -> None:
    """A manually registered plugin can be resolved by name."""
    manager = PluginManager()
    plugin = ToolRegisteringPlugin([])
    manager.register(plugin)

    assert manager.resolve("example_plugin") is plugin


def test_duplicate_registration_raises_exception() -> None:
    """Plugin names are unique within one manager instance."""
    manager = PluginManager()
    manager.register(ToolRegisteringPlugin([]))

    with pytest.raises(DuplicatePluginError, match="example_plugin"):
        manager.register(ToolRegisteringPlugin([]))


@pytest.mark.asyncio
async def test_initialization_registers_plugin_tools() -> None:
    """Plugins receive Tool Manager during initialization."""
    events: list[str] = []
    plugin_manager = PluginManager()
    tool_manager = ToolManager()
    plugin_manager.register(ToolRegisteringPlugin(events))

    await plugin_manager.initialize("example_plugin", tool_manager)

    assert events == ["initialized"]
    assert await tool_manager.execute("plugin_tool", value="Genesis") == "Genesis"


@pytest.mark.asyncio
async def test_shutdown_calls_initialized_plugin() -> None:
    """Initialized plugins can shut down cleanly."""
    events: list[str] = []
    plugin_manager = PluginManager()
    tool_manager = ToolManager()
    plugin_manager.register(ToolRegisteringPlugin(events))
    await plugin_manager.initialize("example_plugin", tool_manager)

    await plugin_manager.shutdown("example_plugin")

    assert events == ["initialized", "shutdown"]


@pytest.mark.asyncio
async def test_unregister_removes_shutdown_plugin() -> None:
    """Plugins can be removed after their lifecycle has ended."""
    plugin_manager = PluginManager()
    tool_manager = ToolManager()
    plugin = ToolRegisteringPlugin([])
    plugin_manager.register(plugin)
    await plugin_manager.initialize("example_plugin", tool_manager)
    await plugin_manager.shutdown("example_plugin")

    assert plugin_manager.unregister("example_plugin") is plugin
    with pytest.raises(PluginNotFoundError):
        plugin_manager.resolve("example_plugin")


def test_unknown_plugin_lookup_raises_exception() -> None:
    """Unknown plugin names provide a meaningful resolution error."""
    with pytest.raises(PluginNotFoundError, match="missing_plugin"):
        PluginManager().resolve("missing_plugin")
