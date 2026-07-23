"""Exceptions raised by the Genesis Plugin System."""


class PluginManagerError(Exception):
    """Base exception for Plugin Manager failures."""


class DuplicatePluginError(PluginManagerError):
    """Raised when a plugin name is registered more than once."""

    def __init__(self, plugin_name: str) -> None:
        super().__init__(f"A plugin named {plugin_name!r} is already registered.")


class PluginNotFoundError(PluginManagerError):
    """Raised when a requested plugin name is not registered."""

    def __init__(self, plugin_name: str) -> None:
        super().__init__(f"No plugin named {plugin_name!r} is registered.")


class PluginAlreadyInitializedError(PluginManagerError):
    """Raised when an initialized plugin is initialized again."""

    def __init__(self, plugin_name: str) -> None:
        super().__init__(f"Plugin {plugin_name!r} is already initialized.")


class PluginNotInitializedError(PluginManagerError):
    """Raised when a plugin is shut down before initialization."""

    def __init__(self, plugin_name: str) -> None:
        super().__init__(f"Plugin {plugin_name!r} is not initialized.")


class PluginStillInitializedError(PluginManagerError):
    """Raised when an active plugin is unregistered before shutdown."""

    def __init__(self, plugin_name: str) -> None:
        super().__init__(f"Plugin {plugin_name!r} must be shut down before unregistration.")


class InvalidPluginNameError(PluginManagerError):
    """Raised when a plugin name is empty or not a string."""
