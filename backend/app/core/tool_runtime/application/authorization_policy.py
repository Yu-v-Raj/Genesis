"""The one place that decides whether a caller may run a tool.

ToolRuntimeManager evaluates this policy before every invocation; there is no other path
to a tool implementation. Checks run in a fixed order and the first failure decides:

1. the context is one of the known caller kinds;
2. the tool exists and is enabled;
3. the caller is eligible: an active Agent that lists the tool in ``allowed_tools``, a
   workflow step that is running and defines exactly this tool and these arguments, or an
   operator test run (no identity, nothing extra granted);
4. every permission the tool declares can actually be enforced (today only ``none``);
5. the arguments satisfy the tool's declared schema;
6. a tool that declares side effects (or doesn't declare) needs an APPROVED, unconsumed
   approval for this exact operation: tool contract, canonical arguments and the caller's
   real identifiers. Without one, the gateway opens (or reuses) a PENDING request and the
   call is held as ``approval_required``. Without a gateway, nothing can be approved.

Evaluating never consumes an approval. ``ToolRuntimeManager.execute`` consumes it, once,
right before the tool runs, after evaluating this policy again at that moment.

What an Agent or workflow step may do is read from their owning runtimes through the
ports below, never from the caller. A port that was never bound denies its callers.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from backend.app.core.approval_gateway.domain.approval import ApprovalGateway, OperationBinding, tool_contract_digest
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.argument_limits import size_problem
from backend.app.core.tool_runtime.domain.argument_schema import matches_schema
from backend.app.core.tool_runtime.domain.authorization import (
    AgentToolContext,
    AuthorizationOutcome,
    DenialReason,
    OperatorTestContext,
    ToolAuthorizationDecision,
    ToolExecutionContext,
    WorkflowToolContext,
)
from backend.app.core.tool_runtime.domain.exceptions import ToolNotFoundError
from backend.app.core.tool_runtime.domain.tool import Tool
from backend.app.core.tool_runtime.domain.tool_permission import ToolPermission


# Permissions this policy can check. A tool declaring anything else cannot run.
ENFORCEABLE_PERMISSIONS = frozenset({ToolPermission.NONE})

MESSAGES: Mapping[DenialReason, str] = MappingProxyType({
    DenialReason.TOOL_NOT_FOUND: "This tool doesn't exist.",
    DenialReason.TOOL_DISABLED: "This tool is disabled.",
    DenialReason.INVALID_CONTEXT: "The request doesn't identify a caller Genesis can authorize.",
    DenialReason.AGENT_NOT_FOUND: "The Agent for this request doesn't exist.",
    DenialReason.AGENT_NOT_ACTIVE: "The Agent isn't in a state where it can use tools.",
    DenialReason.TOOL_NOT_GRANTED: "This Agent isn't allowed to use this tool.",
    DenialReason.STEP_NOT_FOUND: "This workflow step doesn't exist.",
    DenialReason.STEP_NOT_RUNNING: "This workflow step isn't running, so it can't call a tool.",
    DenialReason.STEP_MISMATCH: "The tool call doesn't match what this workflow step defines.",
    DenialReason.PERMISSION_UNENFORCEABLE: "This tool requires permissions Genesis can't check yet, so it can't run.",
    DenialReason.INVALID_ARGUMENTS: "The tool arguments are invalid.",
    DenialReason.ARGUMENTS_TOO_LARGE: "The tool arguments are too large.",
    DenialReason.APPROVAL_REQUIRED: (
        "This tool can affect things outside Genesis, so this exact call needs the operator's approval. "
        "It is waiting in Approvals."
    ),
    DenialReason.APPROVAL_UNUSABLE: "The approval for this call was already used, expired, or no longer matches it.",
    DenialReason.APPROVAL_DENIED: "Running this tool was not approved.",
})


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentToolGrant:
    """What the Agent runtime says an Agent may do right now."""

    allowed_tools: frozenset[str]
    active: bool


class AgentToolGrants(Protocol):
    async def agent_tool_grant(self, agent_id: UUID) -> AgentToolGrant | None:
        """Return the Agent's current grant, or None if the Agent doesn't exist."""
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowStepGrant:
    """The stored contract of one workflow step, as the Workflow runtime persisted it."""

    tool_name: str
    arguments: Mapping[str, object] = field(default_factory=dict)
    running: bool
    attempt: int


class WorkflowStepGrants(Protocol):
    async def workflow_step_grant(self, workflow_id: UUID, step_id: str) -> WorkflowStepGrant | None:
        """Return the stored step, or None if the run or step doesn't exist."""
        ...


class ToolAuthorizationPolicy:
    def __init__(self, registry: ToolRegistry, *, approvals: ApprovalGateway | None = None) -> None:
        self._registry = registry
        self._approvals = approvals
        self._agents: AgentToolGrants | None = None
        self._workflows: WorkflowStepGrants | None = None

    def bind_agent_grants(self, source: AgentToolGrants) -> None:
        self._agents = _bind(self._agents, source, "Agent")

    def bind_workflow_steps(self, source: WorkflowStepGrants) -> None:
        self._workflows = _bind(self._workflows, source, "workflow")

    def validate_arguments(self, tool: Tool, arguments: Mapping[str, object]) -> bool:
        return size_problem(arguments) is None and matches_schema(arguments, tool.definition.parameters)

    def argument_problem(self, tool: Tool, arguments: Mapping[str, object]) -> str | None:
        """Why these arguments can't be used with this tool (a limit or the schema), or None."""
        too_large = size_problem(arguments)
        if too_large is not None:
            return too_large
        return None if matches_schema(arguments, tool.definition.parameters) else MESSAGES[DenialReason.INVALID_ARGUMENTS]

    async def evaluate(
        self, context: ToolExecutionContext, tool_name: str, arguments: Mapping[str, object]
    ) -> ToolAuthorizationDecision:
        if not isinstance(context, (AgentToolContext, WorkflowToolContext, OperatorTestContext)):
            return _deny(AuthorizationOutcome.NOT_ALLOWED, DenialReason.INVALID_CONTEXT)
        # Size first: oversized input is refused before any lookup, comparison or approval
        # request touches it.
        too_large = size_problem(arguments)
        if too_large is not None:
            return ToolAuthorizationDecision(
                outcome=AuthorizationOutcome.INVALID_REQUEST, reason=DenialReason.ARGUMENTS_TOO_LARGE, message=too_large
            )
        try:
            tool = self._registry.get(tool_name)
        except ToolNotFoundError:
            return _deny(AuthorizationOutcome.UNAVAILABLE, DenialReason.TOOL_NOT_FOUND)
        if not tool.definition.enabled:
            return _deny(AuthorizationOutcome.UNAVAILABLE, DenialReason.TOOL_DISABLED)

        ineligible = await self._eligibility(context, tool_name, arguments)
        if ineligible is not None:
            return _deny(AuthorizationOutcome.NOT_ALLOWED, ineligible)

        permissions = tool.definition.permissions
        if not permissions or any(permission not in ENFORCEABLE_PERMISSIONS for permission in permissions):
            # An empty declaration is ambiguous, and an unknown one can't be checked: neither runs.
            return _deny(AuthorizationOutcome.NOT_ALLOWED, DenialReason.PERMISSION_UNENFORCEABLE)

        if not self.validate_arguments(tool, arguments):
            return _deny(AuthorizationOutcome.INVALID_REQUEST, DenialReason.INVALID_ARGUMENTS)

        if tool.definition.side_effects is not False:
            return await self._approval(context, tool, arguments)
        return ToolAuthorizationDecision(outcome=AuthorizationOutcome.ALLOWED)

    async def _eligibility(
        self, context: ToolExecutionContext, tool_name: str, arguments: Mapping[str, object]
    ) -> DenialReason | None:
        if isinstance(context, AgentToolContext):
            if self._agents is None:
                return DenialReason.INVALID_CONTEXT
            grant = await self._agents.agent_tool_grant(context.agent_id)
            if grant is None:
                return DenialReason.AGENT_NOT_FOUND
            if not grant.active:
                return DenialReason.AGENT_NOT_ACTIVE
            return None if tool_name in grant.allowed_tools else DenialReason.TOOL_NOT_GRANTED
        if isinstance(context, WorkflowToolContext):
            if self._workflows is None:
                return DenialReason.INVALID_CONTEXT
            step = await self._workflows.workflow_step_grant(context.workflow_id, context.step_id)
            if step is None:
                return DenialReason.STEP_NOT_FOUND
            if not step.running or step.attempt != context.attempt:
                return DenialReason.STEP_NOT_RUNNING
            if step.tool_name != tool_name or not _same_arguments(step.arguments, arguments):
                return DenialReason.STEP_MISMATCH
            return None
        return None  # operator test runs: no identity, so no per-caller grant to check

    async def _approval(
        self, context: ToolExecutionContext, tool: Tool, arguments: Mapping[str, object]
    ) -> ToolAuthorizationDecision:
        if self._approvals is None:
            return ToolAuthorizationDecision(
                outcome=AuthorizationOutcome.APPROVAL_REQUIRED,
                reason=DenialReason.APPROVAL_REQUIRED,
                message="This tool can affect things outside Genesis and needs the operator's approval, which isn't available here.",
            )
        try:
            binding = operation_binding(context, tool, arguments)
        except ValueError:
            return _deny(AuthorizationOutcome.INVALID_REQUEST, DenialReason.INVALID_ARGUMENTS)
        reason = (
            "This tool declares that it can affect things outside Genesis."
            if tool.definition.side_effects is True
            else "This tool doesn't declare whether it has side effects, so it is treated as if it does."
        )
        resolution = await self._approvals.resolve(binding, reason=reason)
        if resolution.approved:
            return ToolAuthorizationDecision(
                outcome=AuthorizationOutcome.ALLOWED,
                approval_id=resolution.approval_id,
                operation_digest=resolution.operation_digest,
            )
        return ToolAuthorizationDecision(
            outcome=AuthorizationOutcome.APPROVAL_REQUIRED,
            reason=DenialReason.APPROVAL_REQUIRED,
            message=MESSAGES[DenialReason.APPROVAL_REQUIRED],
            approval_id=resolution.approval_id,
            operation_digest=resolution.operation_digest,
        )


def operation_binding(context: ToolExecutionContext, tool: Tool, arguments: Mapping[str, object]) -> OperationBinding:
    """The exact operation an approval covers: who asks, with which identifiers, to run
    which tool contract with which canonical arguments."""
    definition = tool.definition
    return OperationBinding(
        caller=context.caller.value,
        subject=subject(context),
        tool_name=definition.name,
        tool_version=definition.version,
        tool_contract=tool_contract_digest(
            definition.parameters,
            side_effects=definition.side_effects,
            permissions=tuple(str(permission) for permission in definition.permissions),
        ),
        arguments=arguments,
    )


def subject(context: ToolExecutionContext) -> dict[str, str]:
    """The identifiers that tie a call to its Agent, workflow step, or execution."""
    if isinstance(context, AgentToolContext):
        ids = {"agent_id": context.agent_id, "interaction_id": context.interaction_id, "execution_id": context.execution_id}
    elif isinstance(context, WorkflowToolContext):
        ids = {"workflow_id": context.workflow_id, "workflow_task_id": context.step_id, "workflow_attempt": context.attempt}
    else:
        ids = {}
    return {key: str(value) for key, value in ids.items() if value is not None}


def _same_arguments(stored: Mapping[str, object], requested: Mapping[str, object]) -> bool:
    """Compare as JSON, so 1, 1.0 and True are different values (Python's == says they're equal)."""
    stored_json, requested_json = _canonical(stored), _canonical(requested)
    return stored_json is not None and stored_json == requested_json


def _canonical(value: Mapping[str, object]) -> str | None:
    def plain(item: object) -> object:
        if isinstance(item, Mapping):
            return {key: plain(inner) for key, inner in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(inner) for inner in item]
        return item

    try:
        return json.dumps(plain(value), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return None  # not plain JSON: never treated as a match


def _deny(outcome: AuthorizationOutcome, reason: DenialReason) -> ToolAuthorizationDecision:
    return ToolAuthorizationDecision(outcome=outcome, reason=reason, message=MESSAGES[reason])


def _bind[T](current: T | None, source: T, kind: str) -> T:
    if current is not None and current != source:
        raise RuntimeError(f"Tool Runtime already has a different {kind} grant source.")
    return source
