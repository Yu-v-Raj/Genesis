"""Exceptions raised by the Genesis runtime lifecycle manager."""

from backend.app.core.runtime.domain.lifecycle import RuntimeState


class RuntimeLifecycleError(Exception):
    """Base exception for runtime lifecycle failures."""


class InvalidRuntimeStateError(RuntimeLifecycleError):
    """Raised when an operation is not valid for the current runtime state."""

    def __init__(self, operation: str, current_state: RuntimeState) -> None:
        super().__init__(
            f"Cannot {operation} while the runtime is {current_state.value}."
        )


class LifecycleHookAlreadyRegisteredError(RuntimeLifecycleError):
    """Raised when a lifecycle hook key is registered more than once."""

    def __init__(self, key: object) -> None:
        super().__init__(f"A lifecycle hook is already registered for key {key!r}.")


class InvalidLifecycleHookError(RuntimeLifecycleError):
    """Raised when a registered service does not implement the hook contract."""

    def __init__(self, key: object) -> None:
        super().__init__(f"Service {key!r} does not implement the lifecycle hook contract.")
