"""Execution Runtime domain exceptions."""

from uuid import UUID


class ExecutionRuntimeError(Exception):
    """Base error for Execution Runtime operations."""


class ExecutionNotFoundError(ExecutionRuntimeError):
    """Raised when an execution cannot be found in bounded history."""

    def __init__(self, execution_id: UUID) -> None:
        super().__init__(f"Execution '{execution_id}' was not found.")


class ExecutionLifecycleError(ExecutionRuntimeError):
    """Raised when an execution lifecycle transition is invalid."""

    def __init__(self, execution_id: UUID, current_state: str, requested_state: str) -> None:
        super().__init__(
            f"Execution '{execution_id}' cannot transition from '{current_state}' to '{requested_state}'."
        )


class AgentNotExecutableError(ExecutionRuntimeError):
    """Raised when an Agent's lifecycle prevents starting a new execution."""

    def __init__(self, agent_id: UUID, reason: str) -> None:
        super().__init__(f"Agent '{agent_id}' cannot execute: {reason}.")
