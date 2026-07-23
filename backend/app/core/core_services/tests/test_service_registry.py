"""Unit tests for the Core service registry."""

import pytest

from backend.app.core.core_services.di import (
    ServiceAlreadyRegisteredError,
    ServiceNotRegisteredError,
)
from backend.app.core.core_services.service_registry import ServiceRegistry


class ExampleService:
    """Simple Core service used to verify registry behavior."""


def test_register_and_resolve_singleton_by_type() -> None:
    """Singleton registrations resolve the same instance each time."""
    registry = ServiceRegistry()
    service = ExampleService()
    registry.register_singleton(ExampleService, service)

    assert registry.resolve(ExampleService) is service
    assert registry.resolve(ExampleService) is service


def test_register_and_resolve_transient_by_key() -> None:
    """Factory registrations create a new instance for every resolution."""
    registry = ServiceRegistry()
    registry.register_factory("transient_service", lambda _: ExampleService())

    assert registry.resolve("transient_service") is not registry.resolve("transient_service")


def test_factory_can_resolve_another_registered_service() -> None:
    """Registry factories can compose services through registry resolution."""
    registry = ServiceRegistry()
    dependency = ExampleService()
    registry.register_singleton(ExampleService, dependency)
    registry.register_factory("consumer", lambda services: services.resolve(ExampleService))

    assert registry.resolve("consumer") is dependency


def test_duplicate_registration_raises_exception() -> None:
    """Service keys cannot be registered more than once."""
    registry = ServiceRegistry()
    registry.register_singleton("service", ExampleService())

    with pytest.raises(ServiceAlreadyRegisteredError):
        registry.register_factory("service", lambda _: ExampleService())


def test_unknown_service_resolution_raises_exception() -> None:
    """Unknown services return the DI container's meaningful error."""
    registry = ServiceRegistry()

    with pytest.raises(ServiceNotRegisteredError, match="missing_service"):
        registry.resolve("missing_service")
