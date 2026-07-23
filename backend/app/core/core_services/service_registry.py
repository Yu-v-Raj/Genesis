"""Centralized registration and resolution of Genesis Core services."""

from collections.abc import Callable
from typing import TypeAlias, TypeVar, overload

from backend.app.core.core_services.di import DependencyContainer


T = TypeVar("T")
ServiceKey: TypeAlias = str | type[object]


class ServiceRegistry:
    """Organize service registrations through a private dependency container."""

    def __init__(self) -> None:
        self._container = DependencyContainer()

    def register_singleton(self, key: ServiceKey, instance: T) -> None:
        """Register one reusable Core service instance for ``key``."""
        self._container.register_singleton(key, instance)

    def register_factory(
        self,
        key: ServiceKey,
        factory: Callable[["ServiceRegistry"], T],
    ) -> None:
        """Register a factory that creates a new Core service per resolution."""
        self._container.register_factory(key, lambda _: factory(self))

    @overload
    def resolve(self, key: type[T]) -> T: ...

    @overload
    def resolve(self, key: str) -> object: ...

    def resolve(self, key: ServiceKey) -> object:
        """Resolve a registered Core service by its string or type key."""
        return self._container.resolve(key)

    def registered_keys(self) -> tuple[ServiceKey, ...]:
        """Return a snapshot of registered Core service keys."""
        return self._container.registered_keys()
