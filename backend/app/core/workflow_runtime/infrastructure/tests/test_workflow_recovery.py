"""Failure injection: workflow runs after a crash — what is kept, re-run, or held for a person."""

import asyncio
from collections import Counter

import pytest

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.tool import Tool
from backend.app.core.tool_runtime.domain.tool_metadata import ToolMetadata
from backend.app.core.tool_runtime.domain.tool_request import ToolRequest
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus
from backend.app.core.workflow_runtime.application.workflow_manager import WorkflowManager
from backend.app.core.workflow_runtime.domain.exceptions import WorkflowRetryError
from backend.app.core.workflow_runtime.domain.models import WorkflowStatus as RS, WorkflowTask, WorkflowTaskStatus as TS
from backend.app.core.workflow_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyWorkflowRepository


LEASE = 0.2


class Gate:
    """Lets a test hold a tool call open, to crash while it is in flight."""

    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.hold: set[str] = set()


async def tools(gate: Gate) -> ToolRuntimeManager:
    bus = EventBus()
    registry = ToolRegistry(bus)
    manager = ToolRuntimeManager(registry, ToolExecutor(registry, bus), bus)

    def handler(name: str):
        async def run(request: ToolRequest) -> ToolResult:
            gate.calls[request.arguments.get("step", name)] += 1
            if request.arguments.get("step") in gate.hold:
                gate.entered.set()
                await gate.release.wait()
            return ToolResult(status=ToolResultStatus.COMPLETED, output={"step": request.arguments.get("step")})
        return run

    for name, side_effects in (("transform", False), ("external_call", True)):
        await manager.register(
            Tool(
                definition=ToolMetadata(name=name, description=f"{name} step", side_effects=side_effects),
                handler=handler(name),
            )
        )
    return manager


def step(task_id: str, tool: str, *deps: str) -> WorkflowTask:
    return WorkflowTask(task_id=task_id, name=task_id, configuration={"tool_name": tool, "tool_arguments": {"step": task_id}}, dependencies=deps)


async def runtime(factory, name: str, gate: Gate) -> WorkflowManager:
    return WorkflowManager(await tools(gate), EventBus(), repository=SqlAlchemyWorkflowRepository(factory), worker_id=name, lease_seconds=LEASE)


async def crash(manager: WorkflowManager) -> None:
    """Stop dead: in-flight steps stay RUNNING in storage, nothing else is written."""
    manager._closing = True
    tasks = [*manager._workers.values(), *([manager._dispatcher] if manager._dispatcher else [])]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def until(manager: WorkflowManager, run_id, status: RS, timeout: float = 3.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while (run := await manager.get(run_id)).status is not status:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"run stayed {run.status}, expected {status}")
        await asyncio.sleep(0.01)
    return run


@pytest.mark.asyncio
async def test_uncertain_side_effect_step_is_held_and_completed_steps_are_never_rerun(session_factory) -> None:
    gate = Gate(); gate.hold.add("call")
    a = await runtime(session_factory, "worker-a", gate)
    definition = await a.create_definition(name="invoice", tasks=(step("read", "transform"), step("call", "external_call", "read"), step("store", "transform", "call")))
    run = await a.create_run(definition.definition_id, start=True)
    await gate.entered.wait()
    await crash(a)

    b = await runtime(session_factory, "worker-b", gate)
    assert await b.recover() == ()  # live lease: not b's to touch yet
    await asyncio.sleep(LEASE * 1.5)
    await b.start_worker()

    held = await b.get(run.workflow_id)
    assert held.status is RS.INTERRUPTED
    assert [(t.task_id, t.status) for t in held.tasks] == [("read", TS.COMPLETED), ("call", TS.INTERRUPTED), ("store", TS.PENDING)]
    assert gate.calls == Counter({"read": 1, "call": 1})  # nothing was re-run automatically
    assert b.retry_decision(held).requires_acknowledgement

    with pytest.raises(WorkflowRetryError) as caught:
        await b.retry(run.workflow_id)
    assert caught.value.requires_acknowledgement

    gate.release.set()
    retried = await b.retry(run.workflow_id, acknowledge_side_effects=True)
    assert retried.attempt == 2
    done = await until(b, run.workflow_id, RS.COMPLETED)

    assert all(t.status is TS.COMPLETED for t in done.tasks)
    assert gate.calls == Counter({"read": 1, "call": 2, "store": 1})  # "read" kept, not repeated
    await b.shutdown()


@pytest.mark.asyncio
async def test_side_effect_free_in_flight_step_resumes_automatically(session_factory) -> None:
    gate = Gate(); gate.hold.add("convert")
    a = await runtime(session_factory, "worker-a", gate)
    run = await a.create(name="convert", tasks=(step("load", "transform"), step("convert", "transform", "load")))
    await a.start(run.workflow_id)
    await gate.entered.wait()
    await crash(a)
    await asyncio.sleep(LEASE * 1.5)

    gate.release.set()
    b = await runtime(session_factory, "worker-b", gate)
    await b.start_worker()
    done = await until(b, run.workflow_id, RS.COMPLETED)

    assert [t.status for t in done.tasks] == [TS.COMPLETED, TS.COMPLETED]
    assert gate.calls == Counter({"load": 1, "convert": 2})
    await b.shutdown()


@pytest.mark.asyncio
async def test_queued_runs_and_paused_runs_survive_a_restart(session_factory) -> None:
    gate = Gate()
    a = await runtime(session_factory, "worker-a", gate)
    queued = await a.create(name="later", tasks=(step("only", "transform"),))
    await a._update(queued.workflow_id, lambda wf: wf.with_updates(status=RS.QUEUED), None)  # queued, never claimed
    created = await a.create(name="draft", tasks=(step("only", "transform"),))

    b = await runtime(session_factory, "worker-b", gate)
    await b.start_worker()

    assert (await until(b, queued.workflow_id, RS.COMPLETED)).tasks[0].result == {"step": "only"}
    assert (await b.get(created.workflow_id)).status is RS.CREATED  # nothing starts on its own
    await b.shutdown()


@pytest.mark.asyncio
async def test_editing_a_definition_never_changes_existing_runs(session_factory) -> None:
    manager = await runtime(session_factory, "worker-a", Gate())
    definition = await manager.create_definition(name="flow", tasks=(step("a", "transform"),))
    old_run = await manager.create_run(definition.definition_id)

    v2 = await manager.update_definition(definition.definition_id, name="flow", tasks=(step("a", "transform"), step("b", "transform", "a")))
    new_run = await manager.create_run(definition.definition_id)

    assert v2.version == 2
    assert [t.task_id for t in (await manager.get(old_run.workflow_id)).tasks] == ["a"]
    assert (await manager.get(old_run.workflow_id)).definition_version == 1
    assert [t.task_id for t in new_run.tasks] == ["a", "b"]
    assert [t.task_id for t in (await manager.get_definition(definition.definition_id, 1)).tasks] == ["a"]


@pytest.mark.asyncio
async def test_failed_step_blocks_dependents_and_retry_reruns_only_unfinished_steps(session_factory) -> None:
    gate = Gate()
    manager = await runtime(session_factory, "worker-a", gate)
    run = await manager.create(
        name="fails",
        tasks=(step("ok", "transform"), step("bad", "transform", "ok"), step("after", "transform", "bad")),
    )
    original = manager._tools.execute

    async def failing_once(**kwargs):
        if kwargs["arguments"].get("step") == "bad" and gate.calls["bad-failed"] == 0:
            gate.calls["bad-failed"] += 1
            raise RuntimeError("upstream unavailable")
        return await original(**kwargs)

    manager._tools.execute = failing_once  # type: ignore[method-assign]
    await manager.start(run.workflow_id)
    failed = await until(manager, run.workflow_id, RS.FAILED)

    assert [(t.task_id, t.status) for t in failed.tasks] == [("ok", TS.COMPLETED), ("bad", TS.FAILED), ("after", TS.BLOCKED)]
    assert not manager.retry_decision(failed).requires_acknowledgement
    await manager.retry(run.workflow_id)
    done = await until(manager, run.workflow_id, RS.COMPLETED)
    assert gate.calls["ok"] == 1 and gate.calls["after"] == 1
    assert done.attempt == 2
    await manager.shutdown()
