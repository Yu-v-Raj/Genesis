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
