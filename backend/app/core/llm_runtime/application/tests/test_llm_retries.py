"""Model requests are retried only for transient failures, within fixed bounds, and a
retry never repeats a tool call or uses an approval twice.

Deterministic fake providers; the backoff ``sleep`` is recorded instead of waited.
"""

import asyncio
import json
from collections import Counter
from uuid import NAMESPACE_URL, uuid5

import pytest

from backend.app.core.agent_runtime.application.agent_interaction_service import AgentInteractionService
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.application.chat_work import ChatWorkHandler
from backend.app.core.approval_gateway.domain.approval import ApprovalResolution, ApprovalState, OperationBinding
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.llm_runtime.application.llm_manager import LLMManager, RetryPolicy
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseNormalizationError,
    LLMTimeoutError,
    LLMTransientError,
)
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, Message, MessageRole, ToolCall
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.tool import builtin_tools


MODEL = LLMModel(provider="fake", model_name="fake-1")
SECRET = "sk-THISMUSTNEVERAPPEARINEVENTS1234"
PROMPT = "my private question about payroll"
POLICY = RetryPolicy(max_attempts=3, base_delay=0.5, max_delay=8.0, total_timeout=60.0)


class Scripted(LLMProvider):
    """Returns or raises the scripted outcomes in order; ``hang`` never returns."""

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (MODEL,)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if outcome == "hang":
            await asyncio.Event().wait()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome  # type: ignore[return-value]


class Harness:
    def __init__(self, provider: Scripted, policy: RetryPolicy | None = POLICY) -> None:
        self.provider = provider
        self.events: list = []
        self.sleeps: list[float] = []
        bus = EventBus()
        bus.subscribe(self.events.append)
        registry = LLMProviderRegistry()
        registry.register(provider)

        async def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        self.bus = bus
        self.llm = LLMManager(registry, bus, retry=policy, sleep=sleep, jitter=lambda: 1.0) if policy else LLMManager(registry, bus, sleep=sleep)

    def of(self, event_type: str) -> list[dict]:
        return [dict(event.payload) for event in self.events if event.event_type == event_type]


def request() -> LLMRequest:
    return LLMRequest(model=MODEL, messages=(Message(role=MessageRole.USER, content=PROMPT),), metadata={"agent_id": "a1", "interaction_id": "i1"})


def ok(content: str = "fine") -> LLMResponse:
    return LLMResponse(content=content, model=MODEL)


@pytest.mark.asyncio
async def test_a_first_attempt_success_makes_one_call() -> None:
    harness = Harness(Scripted(ok()))
    assert (await harness.llm.generate(request())).content == "fine"
    assert harness.provider.calls == 1 and harness.sleeps == []
    (done,) = harness.of("llm.completed")
    assert done["attempts"] == 1 and done["interaction_id"] == "i1" and harness.of("llm.retrying") == []


@pytest.mark.asyncio
async def test_a_transient_failure_is_retried_with_backoff_then_succeeds() -> None:
    harness = Harness(Scripted(LLMTransientError("overloaded"), LLMRateLimitError("slow down"), ok()))
    assert (await harness.llm.generate(request())).content == "fine"

    assert harness.provider.calls == 3
    assert harness.sleeps == [0.5, 1.0]  # exponential: base, then 2 x base
    retries = harness.of("llm.retrying")
    assert [(r["attempt"], r["error_category"], r["delay_ms"]) for r in retries] == [(1, "provider_unavailable", 500), (2, "rate_limited", 1000)]
    assert harness.of("llm.completed")[0]["attempts"] == 3 and harness.of("llm.failed") == []


@pytest.mark.asyncio
async def test_retries_stop_at_the_attempt_limit_and_say_so() -> None:
    harness = Harness(Scripted(*(LLMTransientError("503") for _ in range(3)), ok()))
    with pytest.raises(LLMTransientError, match="Gave up after 3 attempts"):
        await harness.llm.generate(request())

    assert harness.provider.calls == 3 and len(harness.sleeps) == 2
    (failed,) = harness.of("llm.failed")
    assert (failed["attempts"], failed["retries_exhausted"], failed["error_category"]) == (3, True, "provider_unavailable")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [LLMConfigurationError("bad key"), LLMProviderError("HTTP 400"), LLMResponseNormalizationError("garbled"), RuntimeError("bug")],
)
async def test_permanent_failures_are_not_retried(error: Exception) -> None:
    harness = Harness(Scripted(error, ok()))
    with pytest.raises(type(error)) as caught:
        await harness.llm.generate(request())
    assert caught.value is error  # surfaced unchanged
    assert harness.provider.calls == 1 and harness.sleeps == []
    (failed,) = harness.of("llm.failed")
    assert failed["attempts"] == 1 and failed["retries_exhausted"] is False


@pytest.mark.asyncio
async def test_the_providers_retry_after_is_honoured_but_capped() -> None:
    harness = Harness(Scripted(LLMRateLimitError("429", retry_after=3.0), LLMRateLimitError("429", retry_after=600.0), ok()))
    await harness.llm.generate(request())
    assert harness.sleeps == [3.0, 8.0]


def test_backoff_is_bounded_and_jittered() -> None:
    policy = RetryPolicy(max_attempts=5, base_delay=1.0, max_delay=4.0)
    error = LLMTransientError("x")
    assert [policy.delay(attempt, error, 1.0) for attempt in (1, 2, 3, 4)] == [1.0, 2.0, 4.0, 4.0]
    assert policy.delay(3, error, 0.25) == 1.0
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)


@pytest.mark.asyncio
async def test_without_a_policy_a_request_is_attempted_once() -> None:
    harness = Harness(Scripted(LLMTransientError("503"), ok()), policy=None)
    with pytest.raises(LLMTransientError):
        await harness.llm.generate(request())
    assert harness.provider.calls == 1


@pytest.mark.asyncio
async def test_a_hung_provider_times_out_within_the_overall_deadline() -> None:
    harness = Harness(Scripted("hang", ok()), policy=RetryPolicy(max_attempts=3, base_delay=5.0, max_delay=5.0, total_timeout=0.05))
    with pytest.raises(LLMTimeoutError, match="did not respond within 0.05 s"):
        await harness.llm.generate(request())
    # The retry's backoff would overrun the deadline, so no second attempt is made.
    assert harness.provider.calls == 1 and harness.sleeps == []
    assert harness.of("llm.failed")[0]["error_category"] == "timeout"


@pytest.mark.asyncio
async def test_cancellation_is_recorded_and_never_retried() -> None:
    harness = Harness(Scripted("hang", ok()))
    call = asyncio.create_task(harness.llm.generate(request()))
    while harness.provider.calls == 0:
        await asyncio.sleep(0)
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    assert harness.provider.calls == 1
    (failed,) = harness.of("llm.failed")
    assert failed["error_category"] == "cancelled" and harness.of("llm.completed") == []


@pytest.mark.asyncio
async def test_events_carry_no_credentials_prompts_or_provider_messages() -> None:
    harness = Harness(Scripted(LLMTransientError(f"upstream said {SECRET} for {PROMPT}"), LLMProviderError(f"key {SECRET}")))
    with pytest.raises(LLMProviderError):
        await harness.llm.generate(request())
    dumped = json.dumps([dict(event.payload) for event in harness.events])
    assert SECRET not in dumped and PROMPT not in dumped and "upstream said" not in dumped
    assert {"llm.requested", "llm.retrying", "llm.failed"} <= {event.event_type for event in harness.events}


def test_agent_work_records_the_normalized_category() -> None:
    handler = ChatWorkHandler.__new__(ChatWorkHandler)
    assert handler.error_category(LLMRateLimitError("x")) == "rate_limited"
    assert handler.error_category(LLMTransientError("x")) == "provider_unavailable"
    assert handler.error_category(LLMTimeoutError("x")) == "timeout"
    assert handler.error_category(LLMProviderError("x")) == "provider_error"
    assert handler.error_category(LLMConfigurationError("x")) == "configuration"


# ------------------------------------------------- retries and tool side effects


class CountingApprovals:
    """An approval already granted for any call, counting how often it is used."""

    def __init__(self) -> None:
        self.consumed: Counter[str] = Counter()

    async def resolve(self, binding: OperationBinding, *, reason: str) -> ApprovalResolution:
        return ApprovalResolution(approval_id=uuid5(NAMESPACE_URL, binding.digest), state=ApprovalState.APPROVED, operation_digest=binding.digest)

    async def consume(self, approval_id, operation_digest) -> bool:
        self.consumed[str(approval_id)] += 1
        return True

    async def record_outcome(self, approval_id, **_: object) -> None:
        return None

    async def state_of(self, approval_id) -> ApprovalState:
        return ApprovalState.APPROVED

    async def cancel(self, approval_id, *, reason: str) -> None:
        return None


@pytest.mark.asyncio
async def test_retrying_the_model_after_a_tool_ran_never_repeats_the_tool_or_its_approval() -> None:
    approvals = CountingApprovals()
    bus = EventBus()
    tool_registry = ToolRegistry(bus)
    tools = ToolRuntimeManager(tool_registry, ToolExecutor(tool_registry, bus), bus, approvals=approvals)
    for tool in builtin_tools():
        await tools.register(tool)
    provider = Scripted(
        LLMResponse(content=None, model=MODEL, tool_calls=(ToolCall(call_id="c1", name="simulated_action", arguments={"note": "ship it"}),)),
        LLMTransientError("503 while reading the tool result"),
        LLMRateLimitError("429"),
        ok("Shipped."),
    )
    providers = LLMProviderRegistry()
    providers.register(provider)
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    agents = AgentRegistry(bus)
    manager = AgentManager(agents, bus)
    service = AgentInteractionService(agents, manager, LLMManager(providers, bus, retry=POLICY, sleep=sleep, jitter=lambda: 1.0), tool_manager=tools)
    agent = await manager.create_agent(name="a", description="d", type="chat", llm_model=MODEL, allowed_tools=("simulated_action",))
    await manager.initialize_agent(agent.id)

    _, response = await service.chat(agent.id, "Ship it.")

    assert response.content == "Shipped."
    assert provider.calls == 4 and len(sleeps) == 2  # the second model request was retried twice
    (task,) = tools.history()  # the tool ran exactly once
    assert task.tool_name == "simulated_action" and task.status.value == "completed"
    assert list(approvals.consumed.values()) == [1]  # its approval was used exactly once
