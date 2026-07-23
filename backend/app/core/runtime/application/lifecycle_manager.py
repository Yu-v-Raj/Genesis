"""Application service coordinating the Genesis runtime lifecycle."""

import asyncio

from backend.app.core.core_services.service_registry import ServiceKey, ServiceRegistry
from backend.app.core.runtime.domain.exceptions import (
    InvalidLifecycleHookError,
    InvalidRuntimeStateError,
    LifecycleHookAlreadyRegisteredError,
)
from backend.app.core.runtime.domain.lifecycle import LifecycleHook, RuntimeState


class RuntimeLifecycleManager:
    """Coordinate lifecycle hooks resolved through the Core service registry."""

    def __init__(self, service_registry: ServiceRegistry) -> None:
        self._service_registry = service_registry
        self._state = RuntimeState.CREATED
        self._hook_keys: list[ServiceKey] = []
        self._transition_lock = asyncio.Lock()

    @property
    def state(self) -> RuntimeState:
        """Return the runtime's current lifecycle state."""
        return self._state

    def register_hook(self, key: ServiceKey) -> None:
        """Register a Core service key for future lifecycle participation."""
        if self._state is not RuntimeState.CREATED:
            raise InvalidRuntimeStateError("register lifecycle hooks", self._state)
        if key in self._hook_keys:
            raise LifecycleHookAlreadyRegisteredError(key)
        self._hook_keys.append(key)

    async def startup(self) -> None:
        """Start registered lifecycle hooks in registration order."""
        async with self._transition_lock:
            self._require_state("start", RuntimeState.CREATED)
            self._state = RuntimeState.STARTING
            try:
                for hook in self._resolve_hooks():
                    await hook.startup()
            except Exception:
                self._state = RuntimeState.CREATED
                raise
            self._state = RuntimeState.RUNNING

    async def shutdown(self) -> None:
        """Shut down registered lifecycle hooks in reverse registration order."""
        async with self._transition_lock:
            self._require_state("shut down", RuntimeState.RUNNING)
            self._state = RuntimeState.STOPPING
            error: Exception | None = None
            for hook in reversed(self._resolve_hooks()):
                try:
                    await hook.shutdown()
                except Exception as hook_error:
                    if error is None:
                        error = hook_error
            self._state = RuntimeState.STOPPED
            if error is not None:
                raise error

    def _resolve_hooks(self) -> list[LifecycleHook]:
        hooks: list[LifecycleHook] = []
        for key in self._hook_keys:
            service = self._service_registry.resolve(key)
            if not isinstance(service, LifecycleHook):
                raise InvalidLifecycleHookError(key)
            hooks.append(service)
        return hooks

    def _require_state(self, operation: str, expected_state: RuntimeState) -> None:
        if self._state is not expected_state:
            raise InvalidRuntimeStateError(operation, self._state)
