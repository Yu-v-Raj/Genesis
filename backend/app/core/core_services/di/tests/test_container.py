"""Unit tests for the dependency injection container."""

from concurrent.futures import ThreadPoolExecutor

from backend.app.core.core_services.di.container import DependencyContainer
from backend.app.core.core_services.di.exceptions import (
    ServiceAlreadyRegisteredError,
    ServiceNotRegisteredError,
)


class ExampleService:
    """Simple service used to validate type-key registration."""


def test_resolve_singleton_by_type() -> None:
    """Singleton registrations return the same object for each resolution."""
    container = DependencyContainer()
    service = ExampleService()
    container.register_singleton(ExampleService, service)

    assert container.resolve(ExampleService) is service
    assert container.resolve(ExampleService) is service


def test_resolve_transient_factory_by_key() -> None:
    """Factory registrations create a fresh object for every resolution."""
    container = DependencyContainer()
    container.register_factory("request_context", lambda _: object())

    assert container.resolve("request_context") is not container.resolve("request_context")


def test_factory_can_resolve_registered_dependencies() -> None:
    """Factories can compose services through the same container."""
    container = DependencyContainer()
    dependency = ExampleService()
    container.register_singleton(ExampleService, dependency)
    container.register_factory("consumer", lambda services: services.resolve(ExampleService))

    assert container.resolve("consumer") is dependency


def test_resolving_unknown_service_raises_clear_exception() -> None:
    """Unknown service keys provide a meaningful registration error."""
    container = DependencyContainer()

    try:
        container.resolve("unknown")
    except ServiceNotRegisteredError as error:
        assert "unknown" in str(error)
    else:
        raise AssertionError("Resolving an unknown service should fail.")


def test_duplicate_registration_raises_exception() -> None:
    """A key cannot represent both a singleton and a factory."""
    container = DependencyContainer()
    container.register_singleton("service", ExampleService())

    try:
        container.register_factory("service", lambda _: ExampleService())
    except ServiceAlreadyRegisteredError:
        pass
    else:
        raise AssertionError("Duplicate registration should fail.")


def test_concurrent_registration_allows_only_one_service() -> None:
    """Concurrent registration attempts preserve one unambiguous service binding."""
    container = DependencyContainer()

    def register() -> bool:
        try:
            container.register_singleton("service", ExampleService())
        except ServiceAlreadyRegisteredError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        registrations = list(executor.map(lambda _: register(), range(2)))

    assert registrations.count(True) == 1
    assert registrations.count(False) == 1
