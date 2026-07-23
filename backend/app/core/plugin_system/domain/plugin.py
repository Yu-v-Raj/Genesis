"""Abstract contract for manually registered Genesis plugins."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.core.tool_manager.application.tool_manager import ToolManager


class Plugin(ABC):
    """A named extension that can register tools during initialization."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the plugin's unique registry name."""

    @abstractmethod
    async def initialize(self, tool_manager: "ToolManager") -> None:
        """Initialize the plugin and register any tools it provides."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources owned by the plugin."""
