"""Milestone 1: every tool call passes one server-side policy before the tool can run.

These tests use the real Tool Runtime, Agent registry, and Workflow Runtime. Spy tools
count their invocations, so "denied" is proven by the implementation never being called,
not by a mock of the policy.
"""

import asyncio
from collections import Counter
from collections.abc import Mapping
from uuid import uuid4

import pytest

from backend.app.core.agent_runtime.application.agent_interaction_service import AgentInteractionService
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.application.tool_grants import AgentRegistryToolGrants
from backend.app.core.approval_gateway.application.approval_service import ApprovalService
from backend.app.core.approval_gateway.application.in_memory_repository import InMemoryApprovalRepository
from backend.app.core.approval_gateway.domain.approval import ApprovalState, DecisionSource
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, ToolCall
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.authorization import (
    AgentToolContext,
    AuthorizationOutcome,
    DenialReason,
    OperatorTestContext,
    ToolAuthorizationError,
    WorkflowToolContext,
)
from backend.app.core.tool_runtime.domain.tool import Tool
from backend.app.core.tool_runtime.domain.tool_metadata import ToolMetadata
from backend.app.core.tool_runtime.domain.tool_request import ToolRequest
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus
from backend.app.core.workflow_runtime.application.workflow_manager import WorkflowManager
from backend.app.core.workflow_runtime.domain.exceptions import WorkflowValidationError
from backend.app.core.workflow_runtime.domain.models import WorkflowStatus, WorkflowTask, WorkflowTaskStatus


MODEL = LLMModel(provider="fake", model_name="fake-1")
VALUE_SCHEMA = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}
OPERATOR = OperatorTestContext()


class Runtime:
    """A real Tool Runtime with spy tools, plus the Agent runtime bound as its grant source."""

    def __init__(self, approvals=None) -> None:
        self.bus = EventBus()
        self.events: list = []
        self.bus.subscribe(self.events.append)
        registry = ToolRegistry(self.bus)
        self.tools = ToolRuntimeManager(registry, ToolExecutor(registry, self.bus), self.bus, approvals=approvals)
        self.calls: Counter[str] = Counter()
        self.hold = asyncio.Event()
        self.held = asyncio.Event()
        self.agent_registry = AgentRegistry(self.bus)
        self.agents = AgentManager(self.agent_registry, self.bus)

    async def setup(self) -> "Runtime":
        declarations = {
            "spy": {},
            "spy_other": {},
            "spy_disabled": {"enabled": False},
            "spy_side_effects": {"side_effects": True},
            "spy_undeclared_effects": {"undeclared": True},  # side_effects left at its default
            "spy_no_permissions": {"permissions": ()},
            "spy_unknown_permission": {"permissions": ("network",)},
            "spy_hold": {},
        }
        for name, options in declarations.items():
            undeclared = options.pop("undeclared", False)
            metadata = {"side_effects": False, **options} if not undeclared else {}
            await self.tools.register(
                Tool(
                    definition=ToolMetadata(name=name, description=name, parameters=VALUE_SCHEMA, **metadata),
                    handler=self._handler(name),
                )
            )
        return self

    def _handler(self, name: str):
        async def run(request: ToolRequest) -> ToolResult:
            self.calls[name] += 1
            if name == "spy_hold":
                self.held.set()
                await self.hold.wait()
            return ToolResult(status=ToolResultStatus.COMPLETED, output=request.arguments["value"])
        return run

    def bind_agents(self) -> None:
        self.tools.bind_agent_grants(AgentRegistryToolGrants(self.agent_registry))

    async def agent(self, *allowed: str):
        agent = await self.agents.create_agent(name="a", description="d", type="t", llm_model=MODEL, allowed_tools=allowed)
        return await self.agents.initialize_agent(agent.id)

    def rejected(self) -> list:
        return [event for event in self.events if event.event_type == "tool.rejected"]


async def denied(runtime: Runtime, tool_name: str, context, arguments: Mapping[str, object] | None = None):
    # Bounded, so a policy that wrongly lets a holding tool run fails here instead of hanging.
    call = runtime.tools.execute(tool_name=tool_name, arguments={"value": "x"} if arguments is None else arguments, context=context)
    with pytest.raises(ToolAuthorizationError) as raised:
        await asyncio.wait_for(call, timeout=2)
    return raised.value.decision


# ------------------------------------------------------------------ Agent context


@pytest.mark.asyncio
async def test_an_agent_runs_a_tool_it_is_allowed_to_use() -> None:
    runtime = await Runtime().setup()
    runtime.bind_agents()
    agent = await runtime.agent("spy")

    task = await runtime.tools.execute(tool_name="spy", arguments={"value": "ok"}, context=AgentToolContext(agent_id=agent.id))

    assert task.result is not None and task.result.output == "ok"
    assert runtime.calls["spy"] == 1
    assert task.metadata["caller"] == "agent" and task.metadata["agent_id"] == str(agent.id)


@pytest.mark.asyncio
async def test_agent_denials_never_reach_the_tool_or_create_a_task() -> None:
    runtime = await Runtime().setup()
    runtime.bind_agents()
    agent = await runtime.agent("spy", "spy_disabled")
    context = AgentToolContext(agent_id=agent.id)

    outside = await denied(runtime, "spy_other", context)
    disabled = await denied(runtime, "spy_disabled", context)
    unknown = await denied(runtime, "no_such_tool", context)
    invalid = await denied(runtime, "spy", context, {"value": 7})
    missing = await denied(runtime, "spy", context, {})

    assert (outside.outcome, outside.reason) == (AuthorizationOutcome.NOT_ALLOWED, DenialReason.TOOL_NOT_GRANTED)
    assert (disabled.outcome, disabled.reason) == (AuthorizationOutcome.UNAVAILABLE, DenialReason.TOOL_DISABLED)
    assert (unknown.outcome, unknown.reason) == (AuthorizationOutcome.UNAVAILABLE, DenialReason.TOOL_NOT_FOUND)
    assert (invalid.outcome, invalid.reason) == (AuthorizationOutcome.INVALID_REQUEST, DenialReason.INVALID_ARGUMENTS)
    assert missing.reason is DenialReason.INVALID_ARGUMENTS
    assert sum(runtime.calls.values()) == 0
    assert runtime.tools.history() == ()
    assert not any(event.event_type in {"task.created", "tool.executed"} for event in runtime.events)


@pytest.mark.asyncio
async def test_an_agent_that_cannot_act_is_refused_and_settings_apply_to_the_next_call() -> None:
    runtime = await Runtime().setup()
    runtime.bind_agents()
    agent = await runtime.agent("spy")
    context = AgentToolContext(agent_id=agent.id)
    await runtime.tools.execute(tool_name="spy", arguments={"value": "1"}, context=context)

    await runtime.agents.update_configuration(agent.id, llm_model=MODEL, allowed_tools=(), instructions="")
    revoked = await denied(runtime, "spy", context)
    await runtime.agents.stop_agent(agent.id)
    stopped = await denied(runtime, "spy", context)
    nobody = await denied(runtime, "spy", AgentToolContext(agent_id=uuid4()))

    assert revoked.reason is DenialReason.TOOL_NOT_GRANTED
    assert stopped.reason is DenialReason.AGENT_NOT_ACTIVE
    assert nobody.reason is DenialReason.AGENT_NOT_FOUND
    assert runtime.calls["spy"] == 1


@pytest.mark.asyncio
async def test_agent_context_is_refused_when_no_agent_authority_is_bound() -> None:
    runtime = await Runtime().setup()  # no Agent grant source: nothing can vouch for the Agent
    agent = await runtime.agent("spy")

    decision = await denied(runtime, "spy", AgentToolContext(agent_id=agent.id))

    assert decision.reason is DenialReason.INVALID_CONTEXT
    assert runtime.calls["spy"] == 0


class ScriptedProvider(LLMProvider):
    def __init__(self, *responses: LLMResponse) -> None:
        self._responses = iter(responses)
        self.requests: list[LLMRequest] = []

    @property
    def name(self) -> str:
        return "fake"

    def models(self):
        return (MODEL,)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return next(self._responses)


@pytest.mark.asyncio
async def test_the_model_cannot_run_a_disabled_or_unapproved_tool_even_when_the_agent_lists_it() -> None:
    runtime = await Runtime().setup()
    provider = ScriptedProvider(
        LLMResponse(content=None, model=MODEL, tool_calls=(
            ToolCall(call_id="1", name="spy_disabled", arguments={"value": "x"}),
            ToolCall(call_id="2", name="spy_side_effects", arguments={"value": "x"}),
            ToolCall(call_id="3", name="spy", arguments={"value": "x"}),
        )),
        LLMResponse(content="done", model=MODEL),
    )
    providers = LLMProviderRegistry()
    providers.register(provider)
    service = AgentInteractionService(
        runtime.agent_registry, runtime.agents, LLMManager(providers, runtime.bus), tool_manager=runtime.tools
    )
    agent = await runtime.agent("spy", "spy_disabled", "spy_side_effects")

    _, _, summary = await service.chat_with_summary(agent.id, "go")

    assert [activity.status for activity in summary.tool_activities] == ["rejected", "rejected", "completed"]
    assert summary.tool_activities[1].error == "Requested tool needs a person's approval, which is not available."
    assert dict(runtime.calls) == {"spy": 1}
    assert [(e.payload["reason"], e.payload["caller"]) for e in runtime.rejected()] == [
        ("tool_disabled", "agent"), ("approval_required", "agent"),
    ]


# --------------------------------------------------------------- workflow context


async def workflow_runtime(runtime: Runtime) -> WorkflowManager:
    return WorkflowManager(runtime.tools, runtime.bus)  # binds itself as the step authority


def step(task_id: str, tool: str, value: object = "v", *deps: str) -> WorkflowTask:
    return WorkflowTask(task_id=task_id, name=task_id, configuration={"tool_name": tool, "tool_arguments": {"value": value}}, dependencies=deps)


@pytest.mark.asyncio
async def test_a_workflow_step_runs_its_tool_without_any_agent_identity() -> None:
    runtime = await Runtime().setup()
    workflows = await workflow_runtime(runtime)
    run = await workflows.create(name="ok", tasks=(step("a", "spy", "1"), step("b", "spy", "2", "a")))

    await workflows.start(run.workflow_id)
    done = await workflows.wait(run.workflow_id)

    assert done.status is WorkflowStatus.COMPLETED and [t.result for t in done.tasks] == ["1", "2"]
    assert runtime.calls["spy"] == 2
    for task in runtime.tools.history():
        assert task.metadata["caller"] == "workflow" and task.metadata["workflow_id"] == str(run.workflow_id)
        assert "agent_id" not in task.metadata and task.execution_id is None
    await workflows.shutdown()


@pytest.mark.asyncio
async def test_a_denied_step_fails_the_run_without_running_the_tool_or_retrying() -> None:
    runtime = await Runtime().setup()
    workflows = await workflow_runtime(runtime)
    run = await workflows.create(name="blocked", tasks=(
        step("disabled", "spy_disabled"),
        step("effects", "spy_side_effects"),
        step("after", "spy", "v", "effects"),
    ))

    await workflows.start(run.workflow_id)
    done = await workflows.wait(run.workflow_id)

    by_id = {task.task_id: task for task in done.tasks}
    assert done.status is WorkflowStatus.FAILED and done.attempt == 1
    assert by_id["disabled"].status is WorkflowTaskStatus.FAILED and by_id["disabled"].error == "This tool is disabled."
    assert by_id["effects"].status is WorkflowTaskStatus.FAILED and "needs the operator's approval" in by_id["effects"].error
    assert by_id["after"].status is WorkflowTaskStatus.BLOCKED
    assert sum(runtime.calls.values()) == 0 and runtime.tools.history() == ()
    assert {e.payload["reason"] for e in runtime.rejected()} == {"tool_disabled", "approval_required"}
    assert all(e.payload["caller"] == "workflow" and "agent_id" not in e.payload for e in runtime.rejected())
    await workflows.shutdown()


@pytest.mark.asyncio
async def test_a_workflow_context_only_runs_exactly_its_running_step() -> None:
    runtime = await Runtime().setup()
    workflows = await workflow_runtime(runtime)
    run = await workflows.create(name="held", tasks=(step("hold", "spy_hold", "stored"),))
    context = WorkflowToolContext(workflow_id=run.workflow_id, step_id="hold", attempt=1, lease_owner="local")

    not_started = await denied(runtime, "spy_hold", context, {"value": "stored"})
    await workflows.start(run.workflow_id)
    await runtime.held.wait()  # the real step is now running
    other_tool = await denied(runtime, "spy", context, {"value": "stored"})
    other_arguments = await denied(runtime, "spy_hold", context, {"value": "changed"})
    stale_attempt = await denied(runtime, "spy_hold", WorkflowToolContext(workflow_id=run.workflow_id, step_id="hold", attempt=2, lease_owner="local"), {"value": "stored"})
    no_step = await denied(runtime, "spy_hold", WorkflowToolContext(workflow_id=run.workflow_id, step_id="nope", attempt=1, lease_owner="local"))
    no_run = await denied(runtime, "spy_hold", WorkflowToolContext(workflow_id=uuid4(), step_id="hold", attempt=1, lease_owner="local"))
    other_worker = await denied(runtime, "spy_hold", WorkflowToolContext(workflow_id=run.workflow_id, step_id="hold", attempt=1, lease_owner="stale-worker"), {"value": "stored"})

    assert not_started.reason is DenialReason.STEP_NOT_RUNNING
    assert other_tool.reason is DenialReason.STEP_MISMATCH
    assert other_arguments.reason is DenialReason.STEP_MISMATCH
    assert stale_attempt.reason is DenialReason.STEP_NOT_RUNNING
    assert no_step.reason is no_run.reason is DenialReason.STEP_NOT_FOUND
    assert other_worker.reason is DenialReason.LEASE_NOT_HELD  # a worker that lost the run's lease
    assert runtime.calls == Counter({"spy_hold": 1})  # only the real step

    runtime.hold.set()
    assert (await workflows.wait(run.workflow_id)).status is WorkflowStatus.COMPLETED
    await workflows.shutdown()


@pytest.mark.asyncio
async def test_a_cancelled_run_cannot_start_a_step_tool_and_cancellation_still_terminates_tasks() -> None:
    runtime = await Runtime().setup()
    workflows = await workflow_runtime(runtime)
    run = await workflows.create(name="cancel", tasks=(step("hold", "spy_hold", "v"),))
    await workflows.start(run.workflow_id)
    await runtime.held.wait()

    await workflows.cancel(run.workflow_id)
    for _ in range(200):
        if runtime.tools.history()[0].status.value != "running":
            break
        await asyncio.sleep(0.01)
    late = await denied(runtime, "spy_hold", WorkflowToolContext(workflow_id=run.workflow_id, step_id="hold", attempt=1, lease_owner="local"), {"value": "v"})

    (task,) = runtime.tools.history()
    assert task.status.value == "failed" and task.result is not None and task.result.metadata["cancelled"] is True
    assert late.reason is DenialReason.STEP_NOT_RUNNING
    await workflows.shutdown()


@pytest.mark.asyncio
async def test_workflow_definitions_reject_arguments_their_tool_does_not_accept() -> None:
    runtime = await Runtime().setup()
    workflows = await workflow_runtime(runtime)

    with pytest.raises(WorkflowValidationError, match="doesn't accept"):
        await workflows.create(name="bad", tasks=(step("a", "spy", 42),))
    with pytest.raises(WorkflowValidationError, match="unknown tool"):
        await workflows.create(name="bad", tasks=(step("a", "rm_rf"),))
    assert await workflows.list_definitions() == ()


# --------------------------------------------------------------- operator context


@pytest.mark.asyncio
async def test_operator_tests_run_harmless_tools_and_cannot_claim_an_identity() -> None:
    runtime = await Runtime().setup()

    task = await runtime.tools.execute(
        tool_name="spy",
        arguments={"value": "ok"},
        context=OPERATOR,
        metadata={"agent_id": str(uuid4()), "workflow_id": str(uuid4()), "execution_id": str(uuid4()), "note": "kept"},
    )

    assert task.result is not None and task.result.output == "ok"
    # Caller metadata is kept, but only under its own key: it can't set a trusted field.
    assert set(task.metadata) == {"caller", "caller_metadata"} and task.metadata["caller"] == "operator"
    assert task.metadata["caller_metadata"]["note"] == "kept"
    assert task.execution_id is None


@pytest.mark.asyncio
async def test_operator_tests_cannot_run_disabled_unapproved_or_unenforceable_tools() -> None:
    runtime = await Runtime().setup()

    disabled = await denied(runtime, "spy_disabled", OPERATOR)
    effects = await denied(runtime, "spy_side_effects", OPERATOR)
    undeclared = await denied(runtime, "spy_undeclared_effects", OPERATOR)
    no_permissions = await denied(runtime, "spy_no_permissions", OPERATOR)
    unknown_permission = await denied(runtime, "spy_unknown_permission", OPERATOR)
    invalid = await denied(runtime, "spy", OPERATOR, {"value": ["x"]})

    assert disabled.reason is DenialReason.TOOL_DISABLED
    assert (effects.outcome, effects.reason) == (AuthorizationOutcome.APPROVAL_REQUIRED, DenialReason.APPROVAL_REQUIRED)
    assert undeclared.outcome is AuthorizationOutcome.APPROVAL_REQUIRED  # missing metadata grants nothing
    assert no_permissions.reason is unknown_permission.reason is DenialReason.PERMISSION_UNENFORCEABLE
    assert invalid.reason is DenialReason.INVALID_ARGUMENTS
    assert sum(runtime.calls.values()) == 0 and runtime.tools.history() == ()


@pytest.mark.asyncio
async def test_a_caller_must_name_a_known_context() -> None:
    runtime = await Runtime().setup()

    with pytest.raises(TypeError):
        await runtime.tools.execute(tool_name="spy", arguments={"value": "x"})  # type: ignore[call-arg]
    for impostor in (None, object(), {"caller": "operator"}):
        decision = await denied(runtime, "spy", impostor)
        assert decision.reason is DenialReason.INVALID_CONTEXT
    assert runtime.calls["spy"] == 0
    assert [event.payload["caller"] for event in runtime.rejected()] == ["unknown"] * 3


@pytest.mark.asyncio
async def test_denials_are_recorded_without_arguments() -> None:
    runtime = await Runtime().setup()
    await denied(runtime, "spy_side_effects", OPERATOR, {"value": "secret-value"})

    (event,) = runtime.rejected()
    assert event.payload == {"caller": "operator", "tool_name": "spy_side_effects", "category": "approval_required", "reason": "approval_required"}
    assert "secret-value" not in repr(event.payload)


# ---------------------------------------------------------------------- approval
# Against the real Approval Gateway service (in-memory repository): the policy opens the
# request, the operator decides, and only execute() consumes it, once.

LOCAL = DecisionSource.LOCAL_CONSOLE


def gateway(bus: EventBus | None = None) -> ApprovalService:
    return ApprovalService(InMemoryApprovalRepository(), bus or EventBus())


@pytest.mark.asyncio
async def test_a_side_effect_needs_an_approved_request_and_runs_once() -> None:
    approvals = gateway()
    runtime = await Runtime(approvals=approvals).setup()

    held = await denied(runtime, "spy_side_effects", OPERATOR, {"value": "send"})
    again = await denied(runtime, "spy_side_effects", OPERATOR, {"value": "send"})
    assert held.outcome is AuthorizationOutcome.APPROVAL_REQUIRED and held.approval_id is not None
    assert again.approval_id == held.approval_id  # one pending request per exact operation
    assert (await approvals.get(held.approval_id)).state is ApprovalState.PENDING
    assert runtime.calls["spy_side_effects"] == 0

    await approvals.approve(held.approval_id, source=LOCAL)
    task = await runtime.tools.execute(tool_name="spy_side_effects", arguments={"value": "send"}, context=OPERATOR)
    stored = await approvals.get(held.approval_id)

    assert runtime.calls["spy_side_effects"] == 1
    assert task.metadata["approval_id"] == str(held.approval_id)
    assert stored.state is ApprovalState.CONSUMED and stored.task_id == task.task_id and stored.outcome.value == "completed"
    # The same operation again needs a new decision.
    replay = await denied(runtime, "spy_side_effects", OPERATOR, {"value": "send"})
    assert replay.approval_id != held.approval_id and runtime.calls["spy_side_effects"] == 1


@pytest.mark.asyncio
async def test_a_rejected_request_never_runs_and_is_not_reused() -> None:
    approvals = gateway()
    runtime = await Runtime(approvals=approvals).setup()
    held = await denied(runtime, "spy_side_effects", OPERATOR)

    await approvals.reject(held.approval_id, source=LOCAL)
    after = await denied(runtime, "spy_side_effects", OPERATOR)

    assert after.approval_id != held.approval_id and after.outcome is AuthorizationOutcome.APPROVAL_REQUIRED
    assert runtime.calls["spy_side_effects"] == 0


@pytest.mark.asyncio
async def test_an_approval_covers_only_the_exact_operation() -> None:
    approvals = gateway()
    runtime = await Runtime(approvals=approvals).setup()
    runtime.bind_agents()
    agent = await runtime.agent("spy_side_effects")
    other = await runtime.agent("spy_side_effects")
    held = await denied(runtime, "spy_side_effects", AgentToolContext(agent_id=agent.id), {"value": "a"})
    await approvals.approve(held.approval_id, source=LOCAL)

    changed_arguments = await denied(runtime, "spy_side_effects", AgentToolContext(agent_id=agent.id), {"value": "b"})
    other_agent = await denied(runtime, "spy_side_effects", AgentToolContext(agent_id=other.id), {"value": "a"})
    as_operator = await denied(runtime, "spy_side_effects", OPERATOR, {"value": "a"})

    assert len({held.approval_id, changed_arguments.approval_id, other_agent.approval_id, as_operator.approval_id}) == 4
    assert runtime.calls["spy_side_effects"] == 0
    task = await runtime.tools.execute(tool_name="spy_side_effects", arguments={"value": "a"}, context=AgentToolContext(agent_id=agent.id))
    assert task.metadata["approval_id"] == str(held.approval_id) and runtime.calls["spy_side_effects"] == 1


@pytest.mark.asyncio
async def test_approval_never_overrides_eligibility() -> None:
    approvals = gateway()
    runtime = await Runtime(approvals=approvals).setup()
    runtime.bind_agents()
    agent = await runtime.agent("spy_side_effects")
    held = await denied(runtime, "spy_side_effects", AgentToolContext(agent_id=agent.id))
    await approvals.approve(held.approval_id, source=LOCAL)

    await runtime.agents.update_configuration(agent.id, llm_model=MODEL, allowed_tools=("spy",), instructions="")
    revoked = await denied(runtime, "spy_side_effects", AgentToolContext(agent_id=agent.id))

    assert revoked.reason is DenialReason.TOOL_NOT_GRANTED
    assert (await approvals.get(held.approval_id)).state is ApprovalState.APPROVED  # not consumed by a refused call
    assert runtime.calls["spy_side_effects"] == 0


@pytest.mark.asyncio
async def test_two_concurrent_callers_cannot_both_use_one_approval() -> None:
    approvals = gateway()
    runtime = await Runtime(approvals=approvals).setup()
    held = await denied(runtime, "spy_side_effects", OPERATOR)
    await approvals.approve(held.approval_id, source=LOCAL)

    results = await asyncio.gather(
        *(runtime.tools.execute(tool_name="spy_side_effects", arguments={"value": "x"}, context=OPERATOR) for _ in range(5)),
        return_exceptions=True,
    )

    ran = [result for result in results if not isinstance(result, BaseException)]
    refused = [result for result in results if isinstance(result, ToolAuthorizationError)]
    assert len(ran) == 1 and runtime.calls["spy_side_effects"] == 1
    assert len(refused) == 4 and all(error.decision.outcome is AuthorizationOutcome.APPROVAL_REQUIRED for error in refused)


# ------------------------------------------------------------- undeclared arguments


@pytest.mark.asyncio
async def test_undeclared_arguments_are_refused_on_every_path_before_the_tool_runs() -> None:
    runtime = await Runtime().setup()
    runtime.bind_agents()
    agent = await runtime.agent("spy")
    extra = {"value": "x", "unexpected": "y"}

    as_agent = await denied(runtime, "spy", AgentToolContext(agent_id=agent.id), extra)
    as_operator = await denied(runtime, "spy", OPERATOR, extra)

    workflows = await workflow_runtime(runtime)
    with pytest.raises(WorkflowValidationError, match="doesn't accept"):
        await workflows.create(name="extra", tasks=(
            WorkflowTask(task_id="a", name="a", configuration={"tool_name": "spy", "tool_arguments": extra}),
        ))

    assert as_agent.reason is as_operator.reason is DenialReason.INVALID_ARGUMENTS
    assert as_agent.outcome is AuthorizationOutcome.INVALID_REQUEST
    assert await workflows.list_definitions() == ()
    assert runtime.calls["spy"] == 0 and runtime.tools.history() == ()
    await workflows.shutdown()


@pytest.mark.asyncio
async def test_the_model_cannot_slip_extra_arguments_into_an_allowed_tool() -> None:
    runtime = await Runtime().setup()
    provider = ScriptedProvider(
        LLMResponse(content=None, model=MODEL, tool_calls=(
            ToolCall(call_id="1", name="spy", arguments={"value": "x", "path": "/etc/passwd"}),
        )),
        LLMResponse(content="done", model=MODEL),
    )
    providers = LLMProviderRegistry()
    providers.register(provider)
    service = AgentInteractionService(
        runtime.agent_registry, runtime.agents, LLMManager(providers, runtime.bus), tool_manager=runtime.tools
    )
    agent = await runtime.agent("spy")

    _, _, summary = await service.chat_with_summary(agent.id, "go")

    assert [(a.status, a.error) for a in summary.tool_activities] == [("rejected", "Tool arguments are invalid.")]
    assert runtime.calls["spy"] == 0
    assert [e.payload["reason"] for e in runtime.rejected()] == ["invalid_arguments"]


# --------------------------------------------------- hardening (M1, step equality)


@pytest.mark.asyncio
async def test_caller_metadata_cannot_forge_an_approval_or_identity() -> None:
    runtime = await Runtime().setup()
    forged = {"approval_id": "forged-approval", "caller": "agent", "agent_id": str(uuid4()), "approved": True}

    blocked = await denied_with_metadata(runtime, "spy_side_effects", forged)
    task = await runtime.tools.execute(tool_name="spy", arguments={"value": "x"}, context=OPERATOR, metadata=forged)

    assert blocked.reason is DenialReason.APPROVAL_REQUIRED  # metadata never satisfies approval
    assert runtime.calls["spy_side_effects"] == 0
    assert "approval_id" not in task.metadata and "agent_id" not in task.metadata
    assert task.metadata["caller"] == "operator"
    assert dict(task.metadata["caller_metadata"]) == forged  # kept, but clearly the caller's
    (stored,) = runtime.tools.history()
    assert "approval_id" not in stored.metadata


async def denied_with_metadata(runtime: Runtime, tool_name: str, metadata: dict):
    with pytest.raises(ToolAuthorizationError) as raised:
        await runtime.tools.execute(tool_name=tool_name, arguments={"value": "x"}, context=OPERATOR, metadata=metadata)
    return raised.value.decision


class StoredStep:
    """A running step whose stored arguments are {"count": 1}."""

    async def workflow_step_grant(self, workflow_id, step_id):
        from backend.app.core.tool_runtime.application.authorization_policy import WorkflowStepGrant
        return WorkflowStepGrant(tool_name="counter", arguments={"count": 1}, running=True, attempt=1, lease_owner="local")


@pytest.mark.asyncio
async def test_workflow_step_arguments_must_match_exactly_not_by_python_equality() -> None:
    runtime = await Runtime().setup()
    await runtime.tools.register(Tool(
        definition=ToolMetadata(
            name="counter", description="c", side_effects=False,
            parameters={"type": "object", "properties": {"count": {"type": "number"}}, "required": ["count"]},
        ),
        handler=runtime._handler("counter"),
    ))
    runtime.tools.bind_workflow_steps(StoredStep())
    context = WorkflowToolContext(workflow_id=uuid4(), step_id="s", attempt=1, lease_owner="local")
    policy_check = runtime.tools.authorize

    as_float = await policy_check(tool_name="counter", arguments={"count": 1.0}, context=context)
    as_bool = await policy_check(tool_name="counter", arguments={"count": True}, context=context)
    exact = await policy_check(tool_name="counter", arguments={"count": 1}, context=context)

    assert as_float.reason is as_bool.reason is DenialReason.STEP_MISMATCH  # 1 == 1.0 == True in Python
    assert exact.allowed


@pytest.mark.asyncio
async def test_an_approved_call_that_fails_or_is_cancelled_records_its_outcome() -> None:
    approvals = gateway()
    runtime = await Runtime(approvals=approvals).setup()

    async def failing(request):
        runtime.calls["spy_failing"] += 1
        return ToolResult(status=ToolResultStatus.FAILED, error="downstream refused")

    await runtime.tools.register(Tool(definition=ToolMetadata(name="spy_failing", description="f", parameters=VALUE_SCHEMA), handler=failing))
    held = await denied(runtime, "spy_failing", OPERATOR)
    await approvals.approve(held.approval_id, source=LOCAL)
    task = await runtime.tools.execute(tool_name="spy_failing", arguments={"value": "x"}, context=OPERATOR)
    failed = await approvals.get(held.approval_id)
    assert task.status.value == "failed" and (failed.state, failed.outcome.value) == (ApprovalState.CONSUMED, "failed")

    # Cancelled while the approved tool runs: its effect is unknown and nothing re-runs it.
    await runtime.tools.register(Tool(definition=ToolMetadata(name="spy_slow", description="s", parameters=VALUE_SCHEMA), handler=_holding(runtime)))
    held = await denied(runtime, "spy_slow", OPERATOR)
    await approvals.approve(held.approval_id, source=LOCAL)
    call = asyncio.create_task(runtime.tools.execute(tool_name="spy_slow", arguments={"value": "x"}, context=OPERATOR))
    await runtime.held.wait()
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    cancelled = await approvals.get(held.approval_id)
    assert (cancelled.state, cancelled.outcome.value) == (ApprovalState.CONSUMED, "unknown")
    assert runtime.tools.history()[0].status.value == "failed"  # the task is terminal, never "running"


def _holding(runtime: "Runtime"):
    async def run(request):
        runtime.held.set()
        await asyncio.sleep(30)
        return ToolResult(status=ToolResultStatus.COMPLETED, output="late")
    return run


@pytest.mark.asyncio
async def test_a_stale_attempt_or_duplicate_worker_cannot_use_a_step_approval() -> None:
    approvals = gateway()
    runtime = await Runtime(approvals=approvals).setup()

    class RunningStep:
        attempt = 1

        async def workflow_step_grant(self, workflow_id, step_id):
            from backend.app.core.tool_runtime.application.authorization_policy import WorkflowStepGrant
            return WorkflowStepGrant(tool_name="spy_side_effects", arguments={"value": "x"}, running=True, attempt=self.attempt, lease_owner="local")

    step = RunningStep()
    runtime.tools.bind_workflow_steps(step)
    workflow_id = uuid4()
    first = WorkflowToolContext(workflow_id=workflow_id, step_id="s", attempt=1, lease_owner="local")
    held = await denied(runtime, "spy_side_effects", first)
    await approvals.approve(held.approval_id, source=LOCAL)

    # Two workers that both believe they own the step (e.g. one lost its lease): one call runs.
    results = await asyncio.gather(
        *(runtime.tools.execute(tool_name="spy_side_effects", arguments={"value": "x"}, context=first) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert runtime.calls["spy_side_effects"] == 1

    # A later attempt of the same step is a different operation: it needs its own decision.
    step.attempt = 2
    later = await denied(runtime, "spy_side_effects", WorkflowToolContext(workflow_id=workflow_id, step_id="s", attempt=2, lease_owner="local"))
    stale = await denied(runtime, "spy_side_effects", first)
    assert later.outcome is AuthorizationOutcome.APPROVAL_REQUIRED and later.approval_id != held.approval_id
    assert stale.reason is DenialReason.STEP_NOT_RUNNING
    assert runtime.calls["spy_side_effects"] == 1


# ------------------------------------------------------------- size limits


@pytest.mark.asyncio
async def test_oversized_arguments_are_refused_on_every_path_before_anything_happens() -> None:
    approvals = gateway()
    runtime = await Runtime(approvals=approvals).setup()
    runtime.bind_agents()
    agent = await runtime.agent("spy", "spy_side_effects")
    huge = {"value": "x" * 20_000}

    for tool_name, context in (
        ("spy", AgentToolContext(agent_id=agent.id)),
        ("spy_side_effects", AgentToolContext(agent_id=agent.id)),  # would otherwise open a request
        ("spy_side_effects", OPERATOR),
        ("spy_side_effects", WorkflowToolContext(workflow_id=uuid4(), step_id="s", attempt=1, lease_owner="local")),
    ):
        decision = await denied(runtime, tool_name, context, huge)
        assert decision.reason is DenialReason.ARGUMENTS_TOO_LARGE and decision.outcome is AuthorizationOutcome.INVALID_REQUEST
        assert "16,384" in decision.message and "xxxx" not in decision.message

    assert sum(runtime.calls.values()) == 0 and runtime.tools.history() == ()
    assert await approvals.list() == ()  # no approval request was ever opened
    assert all(e.payload["reason"] == "arguments_too_large" for e in runtime.rejected())


@pytest.mark.asyncio
async def test_workflow_definitions_with_oversized_arguments_are_not_saved() -> None:
    runtime = await Runtime().setup()
    workflows = await workflow_runtime(runtime)

    with pytest.raises(WorkflowValidationError, match="longer than 16,384 characters"):
        await workflows.create(name="big", tasks=(step("a", "spy", "x" * 20_000),))
    assert await workflows.list_definitions() == ()
