"""Abstract contract for tools managed by Genesis Core."""

from abc import ABC, abstractmethod


class Tool(ABC):
    """A named capability that can be invoked asynchronously."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tool's unique registry name."""

    @abstractmethod
    async def execute(self, **arguments: object) -> object:
        """Execute the tool with the supplied named arguments."""
