"""REST adapters for the Approval Gateway: review requests and record operator decisions.

Genesis has no accounts. A decision records the local channel it came through (the
console, identified by its trusted Origin, or a local API client without one); it does
not identify or authenticate a person.
"""

from collections.abc import Mapping
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.exceptions import AgentNotFoundError
from backend.app.core.api.dependencies.system import (
    get_agent_registry,
    get_approval_service,
    get_tool_runtime_manager,
    get_workflow_manager,
)
from backend.app.core.api.schemas.approvals import (
    ApprovalActionResponse,
    ApprovalListResponse,
    ApprovalResponse,
    ApprovalSubjectResponse,
)
from backend.app.core.api.schemas.tools import TaskResponse
from backend.app.core.approval_gateway.application.approval_service import ApprovalService
from backend.app.core.approval_gateway.domain.approval import (
    ACTIVE_STATES,
    Approval,
    ApprovalNotFoundError,
    ApprovalState,
    ApprovalTransitionError,
    DecisionSource,
    redact_arguments,
)
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.domain.authorization import OperatorTestContext, ToolAuthorizationError
from backend.app.core.tool_runtime.domain.task import Task
from backend.app.core.workflow_runtime.application.workflow_manager import WorkflowManager
from backend.app.core.workflow_runtime.domain.exceptions import WorkflowNotFoundError


router = APIRouter(prefix="/api/approvals", tags=["approvals"])
Approvals = Annotated[ApprovalService, Depends(get_approval_service)]
Tools = Annotated[ToolRuntimeManager, Depends(get_tool_runtime_manager)]
Agents = Annotated[AgentRegistry, Depends(get_agent_registry)]
Workflows = Annotated[WorkflowManager, Depends(get_workflow_manager)]


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    approvals: Approvals,
    tools: Tools,
    agents: Agents,
    workflows: Workflows,
    state: Annotated[list[ApprovalState] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ApprovalListResponse:
    """Newest first; filter with ``state`` (repeatable). Expired requests are marked first."""
    items = await approvals.list(states=frozenset(state) if state else None, limit=limit)
    pending = await approvals.list(states=frozenset({ApprovalState.PENDING}), limit=500)
    return ApprovalListResponse(
        approvals=[await approval_response(item, tools, agents, workflows) for item in items],
        pending_count=len(pending),
    )


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(approval_id: UUID, approvals: Approvals, tools: Tools, agents: Agents, workflows: Workflows) -> ApprovalResponse:
    return await approval_response(await _get(approvals, approval_id), tools, agents, workflows)


@router.post("/{approval_id}/approve", response_model=ApprovalActionResponse)
async def approve(
    approval_id: UUID, request: Request, approvals: Approvals, tools: Tools, agents: Agents, workflows: Workflows
) -> ApprovalActionResponse:
    """Approve exactly the stored operation. An Agent's turn or a workflow step resumes on
    its own and uses the approval once; an operator test runs now, once."""
    try:
        approval = await approvals.approve(approval_id, source=_source(request))
    except ApprovalNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ApprovalTransitionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    task, problem = (await _run_operator_test(approval, tools)) if approval.binding.caller == "operator" else (None, None)
    return await _action(approvals, approval_id, tools, agents, workflows, task, problem)


@router.post("/{approval_id}/reject", response_model=ApprovalActionResponse)
async def reject(
    approval_id: UUID, request: Request, approvals: Approvals, tools: Tools, agents: Agents, workflows: Workflows
) -> ApprovalActionResponse:
    try:
        await approvals.reject(approval_id, source=_source(request))
    except ApprovalNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ApprovalTransitionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return await _action(approvals, approval_id, tools, agents, workflows)


@router.post("/{approval_id}/cancel", response_model=ApprovalActionResponse)
async def cancel(
    approval_id: UUID, request: Request, approvals: Approvals, tools: Tools, agents: Agents, workflows: Workflows
) -> ApprovalActionResponse:
    """Withdraw a pending or approved-but-unused request; the waiting work is told it won't run."""
    current = await _get(approvals, approval_id)
    if current.state not in ACTIVE_STATES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"This request is already {current.state.value}.")
    await approvals.cancel(approval_id, reason="Cancelled by the operator.", source=_source(request))
    return await _action(approvals, approval_id, tools, agents, workflows)


@router.post("/{approval_id}/run", response_model=ApprovalActionResponse)
async def run_approved_test(approval_id: UUID, approvals: Approvals, tools: Tools, agents: Agents, workflows: Workflows) -> ApprovalActionResponse:
    """Run an approved operator test that did not run when it was approved (for example
    because Genesis stopped). Never re-runs: the approval can be used only once."""
    current = await _get(approvals, approval_id)
    if current.binding.caller != "operator":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent and workflow requests continue on their own once approved.",
        )
    if current.state is not ApprovalState.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Only an approved, unused request can run; this one is {current.state.value}.")
    task, problem = await _run_operator_test(current, tools)
    return await _action(approvals, approval_id, tools, agents, workflows, task, problem)


# ------------------------------------------------------------------------ helpers


def _source(request: Request) -> DecisionSource:
    # The local request guard has already refused untrusted origins on this POST.
    return DecisionSource.LOCAL_CONSOLE if request.headers.get("origin") else DecisionSource.LOCAL_API


async def _get(approvals: ApprovalService, approval_id: UUID) -> Approval:
    try:
        return await approvals.get(approval_id)
    except ApprovalNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


async def _run_operator_test(approval: Approval, tools: ToolRuntimeManager) -> tuple[Task | None, str | None]:
    """Run the exact stored operation as an operator test, through the full policy; the
    Tool Runtime consumes the approval only if every check still passes."""
    try:
        task = await tools.execute(
            tool_name=approval.binding.tool_name,
            arguments=dict(approval.binding.arguments),
            context=OperatorTestContext(),
        )
    except ToolAuthorizationError as error:
        await tools.cancel_approval(approval.approval_id, reason=f"Not run: {error.decision.message}")
        return None, error.decision.message
    return task, None


async def _action(
    approvals: ApprovalService,
    approval_id: UUID,
    tools: ToolRuntimeManager,
    agents: AgentRegistry,
    workflows: WorkflowManager,
    task: Task | None = None,
    problem: str | None = None,
) -> ApprovalActionResponse:
    stored = await approvals.get(approval_id)
    return ApprovalActionResponse(
        approval=await approval_response(stored, tools, agents, workflows),
        task=None if task is None else TaskResponse.from_task(task),
        problem=problem,
    )


async def approval_response(approval: Approval, tools: ToolRuntimeManager, agents: AgentRegistry, workflows: WorkflowManager) -> ApprovalResponse:
    binding = approval.binding
    shown, redacted = redact_arguments(binding.arguments)
    try:
        description: str | None = tools.get_tool(binding.tool_name).definition.description
    except Exception:
        description = None
    return ApprovalResponse(
        approval_id=approval.approval_id,
        state=approval.state.value,
        caller=binding.caller,
        tool_name=binding.tool_name,
        tool_description=description,
        tool_version=binding.tool_version,
        reason=approval.reason,
        arguments=shown,
        redacted_fields=list(redacted),
        subject=await _subject(binding.subject, agents, workflows),
        created_at=approval.created_at,
        expires_at=approval.expires_at,
        decided_at=approval.decided_at,
        decision_source=None if approval.decision_source is None else approval.decision_source.value,
        consumed_at=approval.consumed_at,
        task_id=approval.task_id,
        outcome=None if approval.outcome is None else approval.outcome.value,
        detail=approval.detail,
        can_decide=approval.state is ApprovalState.PENDING,
        can_cancel=approval.state in ACTIVE_STATES,
        can_run=approval.state is ApprovalState.APPROVED and binding.caller == "operator",
    )


async def _subject(subject: Mapping[str, str], agents: AgentRegistry, workflows: WorkflowManager) -> ApprovalSubjectResponse:
    values = dict(subject)
    agent_id, execution_id, workflow_id = _uuid(values.get("agent_id")), _uuid(values.get("execution_id")), _uuid(values.get("workflow_id"))
    agent_name = workflow_name = step_name = None
    if agent_id is not None:
        try:
            agent_name = agents.get(agent_id).name
        except AgentNotFoundError:
            agent_name = None
    step_id = values.get("workflow_task_id")
    if workflow_id is not None:
        try:
            run = await workflows.get(workflow_id)
            workflow_name = run.name
            step_name = next((task.name for task in run.tasks if task.task_id == step_id), None)
        except WorkflowNotFoundError:
            workflow_name = None
    attempt = values.get("workflow_attempt")
    return ApprovalSubjectResponse(
        agent_id=agent_id,
        agent_name=agent_name,
        execution_id=execution_id,
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        step_id=step_id,
        step_name=step_name,
        attempt=int(attempt) if isinstance(attempt, str) and attempt.isdigit() else None,
    )


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value is not None else None
    except ValueError:
        return None
