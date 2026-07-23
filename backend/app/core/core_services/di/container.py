"""A lightweight, thread-safe dependency injection container."""

from collections.abc import Callable
from threading import RLock
from typing import TypeAlias, TypeVar, cast, overload

from backend.app.core.core_services.di.exceptions import (
    ServiceAlreadyRegisteredError,
    ServiceNotRegisteredError,
)


T = TypeVar("T")
ServiceKey: TypeAlias = str | type[object]
ServiceFactory: TypeAlias = Callable[["DependencyContainer"], object]


class DependencyContainer:
    """Register and resolve application-agnostic services by key or type."""

    def __init__(self) -> None:
        self._singletons: dict[ServiceKey, object] = {}
        self._factories: dict[ServiceKey, ServiceFactory] = {}
        self._lock = RLock()

    def register_singleton(self, key: ServiceKey, instance: T) -> None:
        """Register one reusable service instance for ``key``."""
        self._validate_key(key)
        with self._lock:
            self._ensure_not_registered(key)
            self._singletons[key] = instance

    def register_factory(
        self,
        key: ServiceKey,
        factory: Callable[["DependencyContainer"], T],
    ) -> None:
        """Register a factory that creates a new service instance per resolution."""
        self._validate_key(key)
        if not callable(factory):
            raise TypeError("Service factories must be callable.")
        with self._lock:
            self._ensure_not_registered(key)
            self._factories[key] = cast(ServiceFactory, factory)

    @overload
    def resolve(self, key: type[T]) -> T: ...

    @overload
    def resolve(self, key: str) -> object: ...

    def resolve(self, key: ServiceKey) -> object:
        """Resolve a registered singleton or create a transient service instance."""
        self._validate_key(key)
        with self._lock:
            if key in self._singletons:
                return self._singletons[key]
            factory = self._factories.get(key)

        if factory is None:
            raise ServiceNotRegisteredError(key)

        return factory(self)

    def registered_keys(self) -> tuple[ServiceKey, ...]:
        """Return a snapshot of registered service keys."""
        with self._lock:
            return tuple(self._singletons) + tuple(self._factories)

    def _ensure_not_registered(self, key: ServiceKey) -> None:
        if key in self._singletons or key in self._factories:
            raise ServiceAlreadyRegisteredError(key)

    @staticmethod
    def _validate_key(key: object) -> None:
        if not isinstance(key, str) and not isinstance(key, type):
            raise TypeError("Service keys must be strings or types.")
