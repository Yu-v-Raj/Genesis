"""Bounded Agent coordination across the LLM and Tool runtimes."""

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from uuid import UUID, uuid4

from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.application.context_assembler import AgentContextAssembler
from backend.app.core.agent_runtime.application.tool_grants import AgentRegistryToolGrants
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.exceptions import AgentLifecycleError, AgentUnavailableError
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.agent_runtime.domain.interaction import InteractionSummary, ToolActivity
from backend.app.core.agent_runtime.domain.session import AgentSession
from backend.app.core.agent_runtime.infrastructure.message_codec import (
    decode_tool_call,
    encode_tool_call,
    message_columns,
    message_from_columns,
)
from backend.app.core.approval_gateway.domain.approval import ApprovalState
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.llm_runtime.domain.exceptions import LLMConfigurationError
from backend.app.core.llm_runtime.domain.models import (
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.domain.authorization import (
    AgentToolContext,
    AuthorizationOutcome,
    ToolAuthorizationDecision,
    ToolAuthorizationError,
)
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus


# Persists a checkpoint before a risky step; supplied by the execution worker.
ProgressCallback = Callable[[Mapping[str, object]], Awaitable[None]]


class AgentInteractionService:
    """Coordinate an Agent's bounded LLM-to-Tool interaction loop."""

    DEFAULT_MAX_TOOL_ITERATIONS = 5

    def __init__(
        self,
        agent_registry: AgentRegistry,
        agent_manager: AgentManager,
        llm_manager: LLMManager,
        context_assembler: AgentContextAssembler | None = None,
        tool_manager: ToolRuntimeManager | None = None,
        max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
        memory: MemoryManager | None = None,
    ) -> None:
        if max_tool_iterations < 1:
            raise ValueError("Maximum tool iterations must be positive.")
        self._agent_registry = agent_registry
        self._agent_manager = agent_manager
        self._llm_manager = llm_manager
        self._context_assembler = context_assembler or AgentContextAssembler()
        self._tool_manager = tool_manager
        if tool_manager is not None:
            # The Agent registry is the authority on what each Agent may use; Tool Runtime
            # asks it on every call instead of trusting what the caller claims.
            tool_manager.bind_agent_grants(AgentRegistryToolGrants(agent_registry))
        self._max_tool_iterations = max_tool_iterations
        self._memory = memory

    async def chat(self, agent_id: UUID, message: str, session_id: UUID | None = None) -> tuple[Agent, LLMResponse]:
        """Run an interaction while preserving the established two-value contract."""
        agent, response, _ = await self.chat_with_summary(agent_id, message, session_id)
        return agent, response

    async def prepare(self, agent_id: UUID, session_id: UUID | None = None) -> UUID:
        """Check an Agent can take a message now and return the session it will go to.

        Lets callers reject a request (no model, busy, stopped, unknown session) before
        any durable work is created for it.
        """
        agent = self._agent_registry.get(agent_id)
        if agent.llm_model is None:
            raise LLMConfigurationError("This Agent has no model configured. Choose a model in its settings.")
        _require_available(agent)
        return (await self._agent_manager.get_session(agent_id, session_id)).id

    async def chat_with_summary(
        self,
        agent_id: UUID,
        message: str,
        session_id: UUID | None = None,
        *,
        execution_id: UUID | None = None,
        progress: ProgressCallback | None = None,
        resume: Mapping[str, object] | None = None,
    ) -> tuple[Agent, LLMResponse, InteractionSummary]:
        """Run one IDLE Agent interaction and return its terminal record and LLM response.

        The turn's messages are committed to the session only when the interaction ends
        normally, so a failed request never leaves half a turn in the conversation.

        When run as a durable execution, ``execution_id`` becomes the interaction ID (so
        events, tool tasks, and stored messages correlate with the execution) and
        ``progress`` persists a checkpoint before each tool call.

        If the model asks for a tool call that needs the operator's approval, a durable
        execution raises ``TurnAwaitingApproval`` carrying the turn so far; ``resume``
        (that state) continues the same turn once the request is decided. The tool runs
        only if it was approved, through the same authorization boundary.
        """
        interaction_id = execution_id or uuid4()
        try:
            agent = self._agent_registry.get(agent_id)
            if agent.llm_model is None:
                raise LLMConfigurationError("This Agent has no model configured. Choose a model in its settings.")
            _require_available(agent)
        except Exception:
            if resume is not None:
                # The turn can't continue (Agent stopped, deleted or unconfigured while it
                # waited): its approval must never be used later.
                await self._abandon_awaited(resume, "Not run: the Agent can no longer continue this conversation.")
            raise
        context = await self._agent_manager.get_context(agent_id)
        session = await self._agent_manager.get_session(agent_id, session_id)
        memories = await self._memory.list_memories(agent_id) if self._memory is not None else ()
        system_messages = self._context_assembler.system_messages(agent, memories)
        history = self._context_assembler.history(session.messages)
        if resume is None:
            state = _TurnState(
                turn=[_tagged(item, interaction_id) for item in self._context_assembler.assemble(agent, context, message)],
                session_length=len(session.messages),
            )
        else:
            state = _TurnState.decode(resume)
            # Ordinary history excludes nothing of this turn: it was never committed.
            history = self._context_assembler.history(session.messages[: state.session_length])
        tools = self._tool_definitions(agent)
        try:
            await self._agent_manager.start_agent(agent_id, interaction_id=interaction_id)
        except AgentLifecycleError as error:
            raise AgentUnavailableError(_BUSY_MESSAGE) from error
        usage = LLMResponse(content=None, model=agent.llm_model).usage
        try:
            while True:
                while state.pending_calls:
                    tool_call = state.pending_calls[0]
                    tool_message, activity = await self._tool_result_message(
                        agent,
                        tool_call,
                        interaction_id,
                        execution_id=execution_id,
                        progress=progress,
                        started=state.tools_started,
                        awaited=state.awaiting if state.awaiting and state.awaiting.get("call_id") == tool_call.call_id else None,
                    )
                    state.turn.append(_tagged(tool_message, interaction_id))
                    state.activities.append(activity)
                    state.pending_calls.pop(0)
                    state.awaiting = None
                if state.iterations >= self._max_tool_iterations:
                    limit_response = LLMResponse(
                        content="Tool-call iteration limit reached.",
                        model=agent.llm_model,
                        finish_reason="tool_iteration_limit",
                        usage=usage,
                        metadata={"tool_iteration_limit": self._max_tool_iterations},
                    )
                    state.turn.append(_tagged(self._assistant_tool_call_message(limit_response), interaction_id))
                    await self._commit_turn(agent_id, session, state.turn, state.session_length)
                    return (
                        await self._agent_manager.finish_interaction(agent_id, interaction_id=interaction_id),
                        limit_response,
                        InteractionSummary(interaction_id=interaction_id, session_id=session.id, tool_activities=tuple(state.activities)),
                    )
                response = await self._llm_manager.generate(
                    LLMRequest(
                        model=agent.llm_model,
                        messages=(*system_messages, *history, *state.turn),
                        tools=tools,
                        metadata={"agent_id": str(agent.id), "interaction_id": str(interaction_id)},
                    )
                )
                usage = response.usage
                state.iterations += 1
                state.turn.append(_tagged(self._assistant_tool_call_message(response), interaction_id))
                if not response.tool_calls:
                    await self._commit_turn(agent_id, session, state.turn, state.session_length)
                    return (
                        await self._agent_manager.finish_interaction(agent_id, interaction_id=interaction_id),
                        response,
                        InteractionSummary(interaction_id=interaction_id, session_id=session.id, tool_activities=tuple(state.activities)),
                    )
                state.pending_calls = list(response.tool_calls)
        except _ApprovalNeeded as needed:
            # Nothing ran. Free the Agent; the turn waits durably for the operator, and new
            # messages are refused until it is resolved (see the chat endpoint).
            state.awaiting = {"call_id": needed.call_id, "approval_id": str(needed.approval_id), "tool_name": needed.tool_name}
            await self._agent_manager.finish_interaction(agent_id, interaction_id=interaction_id)
            raise TurnAwaitingApproval(needed.approval_id, needed.tool_name, state.encode()) from None
        except (Exception, asyncio.CancelledError):
            # CancelledError is not an Exception: without it a cancelled chat would leave
            # the Agent RUNNING and unable to take another message.
            await self._agent_manager.finish_interaction(agent_id, interaction_id=interaction_id)
            raise

    async def _abandon_awaited(self, resume: Mapping[str, object], reason: str) -> None:
        awaiting = resume.get("awaiting")
        approval_id = _uuid(awaiting.get("approval_id")) if isinstance(awaiting, Mapping) else None
        if approval_id is not None and self._tool_manager is not None:
            await self._tool_manager.cancel_approval(approval_id, reason=reason)

    async def _commit_turn(self, agent_id: UUID, session: AgentSession, turn: list[Message], session_length: int) -> None:
        """Store the whole turn at once, only if nothing else extended the session meanwhile."""
        await self._agent_manager.append_session_messages(
            agent_id, session.id, *turn, expected_length=session_length
        )

    def _tool_side_effects(self, tool_name: str) -> bool:
        try:
            return bool(self._tool_manager.get_tool(tool_name).definition.side_effects)  # type: ignore[union-attr]
        except Exception:
            return True

    def _tool_definitions(self, agent: Agent) -> tuple[ToolDefinition, ...]:
        if self._tool_manager is None:
            return ()
        return tuple(
            ToolDefinition(
                name=tool.definition.name,
                description=tool.definition.description,
                parameters=tool.definition.parameters,
            )
            for tool in self._tool_manager.list_tools()
            if tool.name in agent.allowed_tools
        )

    @staticmethod
    def _assistant_tool_call_message(response: LLMResponse) -> Message:
        return Message(
            role=MessageRole.ASSISTANT,
            content=response.content or "",
            metadata={"tool_calls": response.tool_calls},
        )

    async def _tool_result_message(
        self,
        agent: Agent,
        tool_call: ToolCall,
        interaction_id: UUID,
        *,
        execution_id: UUID | None = None,
        progress: ProgressCallback | None = None,
        started: list[dict[str, object]] | None = None,
        awaited: Mapping[str, object] | None = None,
    ) -> tuple[Message, ToolActivity]:
        if self._tool_manager is None:
            result = ToolResult(
                tool_name=tool_call.name,
                result={"success": False, "error": "Tool runtime is unavailable."},
            )
            activity = ToolActivity(tool_name=tool_call.name, status="failed", error="Tool runtime is unavailable.")
            return _tool_message(tool_call, result, activity), activity

        approval_id = _uuid(awaited.get("approval_id")) if awaited is not None else None
        if awaited is not None:
            # Resuming after a decision: only an APPROVED request may lead to a call.
            # Anything else is reported to the model without asking for approval again.
            state = None if approval_id is None else await self._tool_manager.approval_state(approval_id)
            if state is ApprovalState.PENDING and approval_id is not None:
                raise _ApprovalNeeded(approval_id, tool_call.call_id, tool_call.name)
            if state is not ApprovalState.APPROVED:
                result, activity = _not_approved(tool_call.name, state)
                return _tool_message(tool_call, result, activity), activity

        context = AgentToolContext(agent_id=agent.id, interaction_id=interaction_id, execution_id=execution_id)
        # Decide before the checkpoint below, so a refused call is never recorded as started.
        decision = await self._tool_manager.authorize(
            tool_name=tool_call.name, arguments=tool_call.arguments, context=context
        )
        if decision.outcome is AuthorizationOutcome.APPROVAL_REQUIRED and decision.approval_id is not None:
            if decision.approval_id != approval_id and execution_id is not None and progress is not None:
                # A durable turn waits for the operator; nothing has run.
                raise _ApprovalNeeded(decision.approval_id, tool_call.call_id, tool_call.name)
        if not decision.allowed:
            if approval_id is not None:
                # Approved, but no longer allowed (allowlist, tool, Agent or approval changed).
                await self._tool_manager.cancel_approval(approval_id, reason=f"Not run: {decision.message}")
            result, activity = _rejected(tool_call.name, decision)
            return _tool_message(tool_call, result, activity), activity

        if progress is not None and started is not None:
            # Checkpoint before the call: if the process dies during it, recovery
            # knows this tool may already have acted. Arguments are not recorded.
            started.append({
                "name": tool_call.name,
                "call_id": tool_call.call_id,
                "side_effects": self._tool_side_effects(tool_call.name),
            })
            await progress({"step": f"tool:{tool_call.name}", "tools_started": list(started)})
        try:
            task = await self._tool_manager.execute(
                tool_name=tool_call.name, arguments=tool_call.arguments, context=context
            )
            execution_result = task.result
            if execution_result is None or execution_result.status is not ToolResultStatus.COMPLETED:
                result = ToolResult(
                    tool_name=tool_call.name,
                    result={"success": False, "error": "Tool execution failed."},
                )
                activity = ToolActivity(
                    tool_name=tool_call.name,
                    status="failed",
                    error="Tool execution failed.",
                    duration=None if execution_result is None else execution_result.duration,
                )
            else:
                result = ToolResult(
                    tool_name=tool_call.name,
                    result={"success": True, "result": execution_result.output},
                )
                activity = ToolActivity(tool_name=tool_call.name, status="completed", result=execution_result.output, duration=execution_result.duration)
        except ToolAuthorizationError as error:
            # The Agent, tool or approval changed between the check above and the call.
            result, activity = _rejected(tool_call.name, error.decision)
        except Exception:
            result = ToolResult(
                tool_name=tool_call.name,
                result={"success": False, "error": "Tool execution failed."},
            )
            activity = ToolActivity(tool_name=tool_call.name, status="failed", error="Tool execution failed.")
        return _tool_message(tool_call, result, activity), activity


class TurnAwaitingApproval(Exception):
    """A chat turn paused before a tool call that needs the operator's approval.

    Nothing ran. ``state`` is the turn so far (JSON-safe) for ``chat_with_summary(resume=...)``.
    """

    def __init__(self, approval_id: UUID, tool_name: str, state: Mapping[str, object]) -> None:
        super().__init__(f"The call to {tool_name} is waiting for the operator's approval.")
        self.approval_id = approval_id
        self.tool_name = tool_name
        self.state = dict(state)


class _ApprovalNeeded(Exception):
    def __init__(self, approval_id: UUID, call_id: str, tool_name: str) -> None:
        super().__init__(tool_name)
        self.approval_id = approval_id
        self.call_id = call_id
        self.tool_name = tool_name


@dataclass
class _TurnState:
    """Everything needed to continue a turn after an approval decision (JSON-safe)."""

    turn: list[Message]
    session_length: int
    pending_calls: list[ToolCall] = field(default_factory=list)
    iterations: int = 0
    activities: list[ToolActivity] = field(default_factory=list)
    tools_started: list[dict[str, object]] = field(default_factory=list)
    awaiting: dict[str, str] | None = None

    def encode(self) -> dict[str, object]:
        return {
            "version": 1,
            "turn": [message_columns(message) for message in self.turn],
            "session_length": self.session_length,
            "pending_calls": [encode_tool_call(call) for call in self.pending_calls],
            "iterations": self.iterations,
            "activities": [
                {"tool_name": a.tool_name, "status": a.status, "result": a.result, "error": a.error, "duration": a.duration}
                for a in self.activities
            ],
            "tools_started": list(self.tools_started),
            "awaiting": self.awaiting,
        }

    @classmethod
    def decode(cls, data: Mapping[str, object]) -> "_TurnState":
        if data.get("version") != 1:
            raise ValueError("This paused conversation turn can't be resumed by this version of Genesis.")
        awaiting = data.get("awaiting")
        return cls(
            turn=[message_from_columns(**dict(item)) for item in data["turn"]],  # type: ignore[arg-type, union-attr]
            session_length=int(data["session_length"]),  # type: ignore[arg-type]
            pending_calls=[decode_tool_call(item) for item in data.get("pending_calls") or []],  # type: ignore[union-attr]
            iterations=int(data.get("iterations") or 0),  # type: ignore[arg-type]
            activities=[ToolActivity(**dict(item)) for item in data.get("activities") or []],  # type: ignore[union-attr]
            tools_started=[dict(item) for item in data.get("tools_started") or []],  # type: ignore[union-attr]
            awaiting={str(k): str(v) for k, v in awaiting.items()} if isinstance(awaiting, Mapping) else None,
        )


def _tool_message(tool_call: ToolCall, result: ToolResult, activity: ToolActivity) -> Message:
    return Message(
        role=MessageRole.TOOL,
        content=json.dumps(result.result),
        metadata={
            "tool_call_id": tool_call.call_id,
            "tool_name": result.tool_name,
            "tool_status": activity.status,
        },
    )


_NOT_APPROVED_MESSAGES = {
    ApprovalState.REJECTED: "The operator rejected this tool call, so it did not run. Don't request it again unless the user asks.",
    ApprovalState.EXPIRED: "The approval request expired before the operator decided, so the tool did not run.",
    ApprovalState.CANCELLED: "The approval request was cancelled, so the tool did not run.",
    ApprovalState.CONSUMED: "This approval was already used, so the tool was not run again.",
}


def _not_approved(tool_name: str, state: ApprovalState | None) -> tuple[ToolResult, ToolActivity]:
    message = _NOT_APPROVED_MESSAGES.get(state, "The approval request no longer exists, so the tool did not run.") if state else (
        "The approval request no longer exists, so the tool did not run."
    )
    return (
        ToolResult(tool_name=tool_name, result={"success": False, "error": message}),
        ToolActivity(tool_name=tool_name, status="rejected", error=message),
    )


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value is not None else None
    except ValueError:
        return None


# What the model is told when a call is refused: generic, so it learns nothing about
# other Agents' tools or the policy's internals.
_REJECTION_MESSAGES = {
    AuthorizationOutcome.UNAVAILABLE: "Requested tool is unavailable.",
    AuthorizationOutcome.NOT_ALLOWED: "Requested tool is not allowed.",
    AuthorizationOutcome.INVALID_REQUEST: "Tool arguments are invalid.",
    AuthorizationOutcome.APPROVAL_REQUIRED: "Requested tool needs a person's approval, which is not available.",
}


def _rejected(tool_name: str, decision: ToolAuthorizationDecision) -> tuple[ToolResult, ToolActivity]:
    message = _REJECTION_MESSAGES.get(decision.outcome, "Requested tool is not allowed.")
    return (
        ToolResult(tool_name=tool_name, result={"success": False, "error": message}),
        ToolActivity(tool_name=tool_name, status="rejected", error=message),
    )


_BUSY_MESSAGE = "This Agent is already working on a request. Wait for it to finish, then try again."
_UNAVAILABLE_MESSAGES = {
    AgentStatus.RUNNING: _BUSY_MESSAGE,
    AgentStatus.CREATED: "This Agent isn't ready yet. Initialize it before chatting.",
    AgentStatus.INITIALIZING: "This Agent is still initializing. Try again in a moment.",
    AgentStatus.STOPPED: "This Agent is stopped and can no longer chat.",
}


def _require_available(agent: Agent) -> None:
    """Explain why a non-IDLE Agent cannot take a new message."""
    if agent.status is AgentStatus.IDLE:
        return
    raise AgentUnavailableError(
        _UNAVAILABLE_MESSAGES.get(agent.status, f"This Agent can't chat while it is {agent.status.value}.")
    )


def _tagged(message: Message, interaction_id: UUID) -> Message:
    """Record which interaction produced a session message."""
    return replace(message, metadata={**message.metadata, "interaction_id": str(interaction_id)})
