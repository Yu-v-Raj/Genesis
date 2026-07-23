"""Application service for manual, in-memory Genesis plugin management."""

import asyncio
from threading import RLock

from backend.app.core.plugin_system.domain.exceptions import (
    DuplicatePluginError,
    InvalidPluginNameError,
    PluginAlreadyInitializedError,
    PluginNotFoundError,
    PluginNotInitializedError,
    PluginStillInitializedError,
)
from backend.app.core.plugin_system.domain.plugin import Plugin
from backend.app.core.tool_manager.application.tool_manager import ToolManager


class PluginManager:
    """Manage manually registered plugins and their tool-registration lifecycle."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._initialized_plugins: set[str] = set()
        self._lock = RLock()
        self._lifecycle_lock = asyncio.Lock()

    def register(self, plugin: Plugin) -> None:
        """Register a plugin under its unique name."""
        if not isinstance(plugin, Plugin):
            raise TypeError("Registered plugins must implement the Plugin base class.")
        self._validate_plugin_name(plugin.name)

        with self._lock:
            if plugin.name in self._plugins:
                raise DuplicatePluginError(plugin.name)
            self._plugins[plugin.name] = plugin

    def unregister(self, plugin_name: str) -> Plugin:
        """Remove and return a plugin that is no longer initialized."""
        self._validate_plugin_name(plugin_name)
        with self._lock:
            if plugin_name in self._initialized_plugins:
                raise PluginStillInitializedError(plugin_name)
            try:
                return self._plugins.pop(plugin_name)
            except KeyError as error:
                raise PluginNotFoundError(plugin_name) from error

    def resolve(self, plugin_name: str) -> Plugin:
        """Return the plugin registered under ``plugin_name``."""
        self._validate_plugin_name(plugin_name)
        with self._lock:
            try:
                return self._plugins[plugin_name]
            except KeyError as error:
                raise PluginNotFoundError(plugin_name) from error

    async def initialize(self, plugin_name: str, tool_manager: ToolManager) -> None:
        """Initialize a plugin so it can register tools with ``tool_manager``."""
        async with self._lifecycle_lock:
            plugin = self.resolve(plugin_name)
            if plugin_name in self._initialized_plugins:
                raise PluginAlreadyInitializedError(plugin_name)
            await plugin.initialize(tool_manager)
            self._initialized_plugins.add(plugin_name)

    async def shutdown(self, plugin_name: str) -> None:
        """Shut down an initialized plugin."""
        async with self._lifecycle_lock:
            plugin = self.resolve(plugin_name)
            if plugin_name not in self._initialized_plugins:
                raise PluginNotInitializedError(plugin_name)
            await plugin.shutdown()
            self._initialized_plugins.remove(plugin_name)

    def registered_names(self) -> tuple[str, ...]:
        """Return a snapshot of registered plugin names."""
        with self._lock:
            return tuple(self._plugins)

    @staticmethod
    def _validate_plugin_name(plugin_name: object) -> None:
        if not isinstance(plugin_name, str) or not plugin_name.strip():
            raise InvalidPluginNameError("Plugin names must be non-empty strings.")
