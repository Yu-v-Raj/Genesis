"""Who is asking to run a tool, and the server's decision about it.

Every call into Tool Runtime names its caller with one of the contexts below. They carry
identifiers only; what the caller may do is looked up from the authoritative records
(the Agent, the stored workflow step), never taken from the context itself.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from backend.app.core.tool_runtime.domain.exceptions import ToolRuntimeError


class ToolCaller(StrEnum):
    AGENT = "agent"
    WORKFLOW = "workflow"
    OPERATOR = "operator"


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentToolContext:
    """A tool call made on behalf of an Agent.

    ``interaction_id`` is set when the Agent's model asked for the call during a chat turn;
    without it the call is execution work queued for the Agent (``tool_name`` metadata).
    """

    agent_id: UUID
    interaction_id: UUID | None = None
    execution_id: UUID | None = None

    @property
    def caller(self) -> ToolCaller:
        return ToolCaller.AGENT


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowToolContext:
    """One step of a workflow run. Workflows have no Agent identity."""

    workflow_id: UUID
    step_id: str
    attempt: int

    @property
    def caller(self) -> ToolCaller:
        return ToolCaller.WORKFLOW


@dataclass(frozen=True, slots=True, kw_only=True)
class OperatorTestContext:
    """A manual test run from the Tools page.

    Genesis does not authenticate operators, so this context carries no identity and
    grants nothing beyond what the policy allows every anonymous test run.
    """

    @property
    def caller(self) -> ToolCaller:
        return ToolCaller.OPERATOR


ToolExecutionContext = AgentToolContext | WorkflowToolContext | OperatorTestContext


class AuthorizationOutcome(StrEnum):
    ALLOWED = "allowed"
    UNAVAILABLE = "unavailable"  # the tool does not exist or is disabled
    NOT_ALLOWED = "not_allowed"  # this caller may not run it, or its requirements can't be met
    INVALID_REQUEST = "invalid_request"  # the arguments don't satisfy the tool's schema
    APPROVAL_REQUIRED = "approval_required"  # needs an approval decision that doesn't exist


class DenialReason(StrEnum):
    """Stable, non-sensitive codes recorded with every denied request."""

    TOOL_NOT_FOUND = "tool_not_found"
    TOOL_DISABLED = "tool_disabled"
    INVALID_CONTEXT = "invalid_context"
    AGENT_NOT_FOUND = "agent_not_found"
    AGENT_NOT_ACTIVE = "agent_not_active"
    TOOL_NOT_GRANTED = "tool_not_granted"
    STEP_NOT_FOUND = "step_not_found"
    STEP_NOT_RUNNING = "step_not_running"
    STEP_MISMATCH = "step_mismatch"
    PERMISSION_UNENFORCEABLE = "permission_unenforceable"
    INVALID_ARGUMENTS = "invalid_arguments"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_DENIED = "approval_denied"


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolAuthorizationDecision:
    outcome: AuthorizationOutcome
    reason: DenialReason | None = None
    # Safe to show to a person or a model: never includes arguments or internal detail.
    message: str = ""
    approval_id: str | None = None

    @property
    def allowed(self) -> bool:
        return self.outcome is AuthorizationOutcome.ALLOWED


class ToolAuthorizationError(ToolRuntimeError):
    """Raised instead of running a tool the policy did not allow. Nothing was executed."""

    def __init__(self, tool_name: str, decision: ToolAuthorizationDecision) -> None:
        super().__init__(decision.message)
        self.tool_name = tool_name
        self.decision = decision
