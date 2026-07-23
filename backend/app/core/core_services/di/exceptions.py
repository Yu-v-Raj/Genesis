"""Exceptions raised by the Genesis dependency injection container."""


class DependencyContainerError(Exception):
    """Base exception for dependency container failures."""


class ServiceAlreadyRegisteredError(DependencyContainerError):
    """Raised when a service key is registered more than once."""

    def __init__(self, key: object) -> None:
        super().__init__(f"A service is already registered for key {key!r}.")


class ServiceNotRegisteredError(DependencyContainerError):
    """Raised when a requested service key has no registration."""

    def __init__(self, key: object) -> None:
        super().__init__(f"No service is registered for key {key!r}.")
