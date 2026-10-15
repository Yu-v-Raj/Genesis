"""The Agent runtime's answer to "which tools may this Agent use right now?"."""

from dataclasses import dataclass
from uuid import UUID

from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.exceptions import AgentNotFoundError
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.tool_runtime.application.authorization_policy import AgentToolGrant


# IDLE covers execution work queued for an Agent; RUNNING covers a chat turn in progress.
# A stopped, paused, failed, or uninitialized Agent can't use tools.
TOOL_USING_STATUSES = frozenset({AgentStatus.IDLE, AgentStatus.RUNNING})


@dataclass(frozen=True, slots=True)
class AgentRegistryToolGrants:
    """Reads the Agent's current record, so a settings change applies to the next call."""

    registry: AgentRegistry

    async def agent_tool_grant(self, agent_id: UUID) -> AgentToolGrant | None:
        try:
            agent = self.registry.get(agent_id)
        except AgentNotFoundError:
            return None
        return AgentToolGrant(allowed_tools=frozenset(agent.allowed_tools), active=agent.status in TOOL_USING_STATUSES)
