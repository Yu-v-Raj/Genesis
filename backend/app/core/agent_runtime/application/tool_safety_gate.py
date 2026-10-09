"""Provider-neutral validation of untrusted LLM tool calls."""

from collections.abc import Mapping

from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.domain.exceptions import ToolNotFoundError
from backend.app.core.tool_runtime.domain.tool import Tool


class ToolSafetyGate:
    """Resolve, authorize, and validate a tool request before execution."""

    def __init__(self, tool_manager: ToolRuntimeManager) -> None:
        self._tool_manager = tool_manager

    def validate(
        self, *, tool_name: str, arguments: Mapping[str, object], allowed_tools: tuple[str, ...]
    ) -> tuple[Tool | None, str | None, str | None]:
        """Return an executable tool or a generic, LLM-safe rejection message."""
        try:
            tool = self._tool_manager.get_tool(tool_name)
        except ToolNotFoundError:
            return None, "Requested tool is unavailable.", "unavailable"
        if tool_name not in allowed_tools:
            return None, "Requested tool is not allowed.", "not_allowed"
        if not _matches_schema(arguments, tool.definition.parameters):
            return None, "Tool arguments are invalid.", "invalid_arguments"
        return tool, None, None


def _matches_schema(value: object, schema: Mapping[str, object]) -> bool:
    """Validate the JSON Schema subset already used by ToolMetadata."""
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, Mapping):
            return False
        required = schema.get("required", ())
        properties = schema.get("properties", {})
        if not isinstance(required, (list, tuple)) or not isinstance(properties, Mapping):
            return False
        if any(not isinstance(name, str) or name not in value for name in required):
            return False
        return all(
            not isinstance(name, str)
            or name not in value
            or not isinstance(property_schema, Mapping)
            or _matches_schema(value[name], property_schema)
            for name, property_schema in properties.items()
        )
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        return (not isinstance(minimum, (int, float)) or value >= minimum) and (
            not isinstance(maximum, (int, float)) or value <= maximum
        )
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type is None:
        return True
    return False
