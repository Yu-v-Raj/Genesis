"""Exceptions raised by the Genesis Tool Manager."""


class ToolManagerError(Exception):
    """Base exception for Tool Manager failures."""


class DuplicateToolError(ToolManagerError):
    """Raised when a tool name is registered more than once."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"A tool named {tool_name!r} is already registered.")


class ToolNotFoundError(ToolManagerError):
    """Raised when a requested tool name is not registered."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"No tool named {tool_name!r} is registered.")


class InvalidToolNameError(ToolManagerError):
    """Raised when a tool name is empty or not a string."""
