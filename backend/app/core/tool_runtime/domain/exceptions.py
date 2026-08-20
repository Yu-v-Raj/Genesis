"""Tool Runtime domain exceptions."""


class ToolRuntimeError(Exception):
    """Base error for Tool Runtime operations."""


class DuplicateToolError(ToolRuntimeError):
    """Raised when a registry name is already occupied."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Tool '{tool_name}' is already registered.")


class ToolNotFoundError(ToolRuntimeError):
    """Raised when a requested Tool is absent from the registry."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Tool '{tool_name}' was not found.")


class ToolDisabledError(ToolRuntimeError):
    """Raised when a disabled Tool is invoked."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Tool '{tool_name}' is disabled.")


class ToolValidationError(ToolRuntimeError):
    """Raised when supplied tool arguments are invalid."""
