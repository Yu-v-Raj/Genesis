"""Exceptions raised by the Agent Runtime registry."""

from uuid import UUID


class AgentRegistryError(Exception):
    """Base error for Agent Runtime registry operations."""


class DuplicateAgentError(AgentRegistryError):
    """Raised when an Agent identifier is already registered."""

    def __init__(self, agent_id: UUID) -> None:
        super().__init__(f"Agent '{agent_id}' is already registered.")


class AgentNotFoundError(AgentRegistryError):
    """Raised when an Agent identifier is not registered."""

    def __init__(self, agent_id: UUID) -> None:
        super().__init__(f"Agent '{agent_id}' is not registered.")


class AgentLifecycleError(AgentRegistryError):
    """Raised when an Agent lifecycle transition is not permitted."""

    def __init__(self, agent_id: UUID, current_state: str, requested_state: str) -> None:
        super().__init__(
            f"Agent '{agent_id}' cannot transition from '{current_state}' to '{requested_state}'."
        )


class AgentUnavailableError(AgentLifecycleError):
    """Raised with a user-facing reason when an Agent cannot accept a request now."""

    def __init__(self, message: str) -> None:
        AgentRegistryError.__init__(self, message)


class AgentConfigurationError(AgentRegistryError):
    """Raised when an Agent's LLM or tool configuration is invalid."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


class SessionNotFoundError(AgentRegistryError):
    """Raised when a session does not exist or belongs to a different Agent."""

    def __init__(self, session_id: UUID) -> None:
        super().__init__(f"Session '{session_id}' was not found for this Agent.")
