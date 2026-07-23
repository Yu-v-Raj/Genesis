"""Exceptions raised by the Genesis Memory Framework."""


class MemoryManagerError(Exception):
    """Base exception for Memory Manager failures."""


class DuplicateMemoryProviderError(MemoryManagerError):
    """Raised when a provider name is registered more than once."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(f"A memory provider named {provider_name!r} is already registered.")


class MemoryProviderNotFoundError(MemoryManagerError):
    """Raised when a requested provider name is not registered."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(f"No memory provider named {provider_name!r} is registered.")


class InvalidMemoryProviderNameError(MemoryManagerError):
    """Raised when a provider name is empty or not a string."""
