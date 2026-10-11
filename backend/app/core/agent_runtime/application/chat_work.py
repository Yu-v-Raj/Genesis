"""Agent chat turns as durable Execution Runtime work (``metadata["kind"] == "chat"``).

The Execution Runtime owns the lifecycle (queue, lease, timeline, retry); this handler
only performs one chat turn through ``AgentInteractionService``, which keeps the Agent
lifecycle, the safety gate, Tool Runtime, and atomic session commits exactly as they are.
"""

from collections.abc import Mapping
from uuid import UUID

from backend.app.core.agent_runtime.application.agent_interaction_service import AgentInteractionService
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.domain.exceptions import (
    AgentLifecycleError,
    AgentNotFoundError,
    SessionNotFoundError,
)
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_context import ExecutionContext
from backend.app.core.execution_runtime.domain.work import RecoveryVerdict, WorkOutcome
from backend.app.core.llm_runtime.domain.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMTimeoutError,
    ProviderNotFoundError,
)
from backend.app.core.llm_runtime.domain.models import MessageRole


CHAT_KIND = "chat"


def chat_metadata(message: str, session_id: UUID) -> dict[str, object]:
    """The durable input of a chat execution: enough to run (or retry) the turn later."""
    return {"kind": CHAT_KIND, "message": message, "session_id": str(session_id)}


class ChatWorkHandler:
    def __init__(self, interaction: AgentInteractionService, agents: AgentManager) -> None:
        self._interaction = interaction
        self._agents = agents

    async def run(self, context: ExecutionContext) -> WorkOutcome:
        message = context.metadata.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("A chat execution needs a message.")
        agent, response, summary = await self._interaction.chat_with_summary(
            context.agent_id,
            message,
            _session_id(context.metadata),
            execution_id=context.execution_id,
            progress=context.report_progress,
        )
        return WorkOutcome(output=response.content or "", value=(agent, response, summary))

    def may_have_side_effects(self, metadata: Mapping[str, object], checkpoint: Mapping[str, object]) -> bool:
        """Model calls change nothing outside Genesis; only tools that started can.

        The checkpoint is written before each tool call, so a tool that never appears in
        it cannot have run.
        """
        started = checkpoint.get("tools_started")
        if not isinstance(started, list):
            return False
        return any(not isinstance(tool, Mapping) or tool.get("side_effects", True) for tool in started)

    def error_category(self, error: BaseException) -> str:
        if isinstance(error, (LLMConfigurationError, ProviderNotFoundError)):
            return "configuration"
        if isinstance(error, LLMTimeoutError):
            return "timeout"
        if isinstance(error, LLMProviderError):
            return "provider_error"
        if isinstance(error, AgentLifecycleError):
            return "agent_unavailable"
        if isinstance(error, (SessionNotFoundError, AgentNotFoundError, ValueError)):
            return "invalid_request"
        if isinstance(error, PersistenceConflictError):
            return "conflict"
        if isinstance(error, PersistenceError):
            return "storage"
        return "chat_failed"

    async def reconcile(self, execution: Execution) -> RecoveryVerdict:
        """Did the turn get saved before the process stopped?

        Session messages carry ``interaction_id == execution_id``. If the turn is in the
        session, the chat finished and only marking the execution done was lost.
        """
        session_id = _session_id(execution.metadata)
        if session_id is None:
            return RecoveryVerdict(completed=False)
        try:
            session = await self._agents.get_session(execution.agent_id, session_id)
        except (AgentNotFoundError, SessionNotFoundError):
            return RecoveryVerdict(completed=False)
        turn = [m for m in session.messages if m.metadata.get("interaction_id") == str(execution.execution_id)]
        if not turn:
            return RecoveryVerdict(completed=False)
        reply = next((m.content for m in reversed(turn) if m.role is MessageRole.ASSISTANT and m.content), "")
        return RecoveryVerdict(completed=True, output=reply, detail="the chat turn was already saved to the session")


def _session_id(metadata: Mapping[str, object]) -> UUID | None:
    value = metadata.get("session_id")
    try:
        return UUID(value) if isinstance(value, str) else None
    except ValueError:
        return None
