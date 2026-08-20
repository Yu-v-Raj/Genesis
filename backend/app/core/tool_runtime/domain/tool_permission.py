"""Permissions declared by tools for future policy enforcement."""

from enum import StrEnum


class ToolPermission(StrEnum):
    """Permissions required to invoke a Tool."""

    NONE = "none"
