"""Tool availability and invocation result statuses."""

from enum import StrEnum


class ToolStatus(StrEnum):
    """Whether a registered Tool is available for invocation."""

    ENABLED = "enabled"
    DISABLED = "disabled"


class ToolResultStatus(StrEnum):
    """Terminal outcome statuses returned by tool execution."""

    COMPLETED = "completed"
    FAILED = "failed"
