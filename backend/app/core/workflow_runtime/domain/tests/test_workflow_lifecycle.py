"""Workflow run state machine, retry policy, and definition snapshots."""

from backend.app.core.workflow_runtime.domain.lifecycle import (
    FINAL_RUN_STATUSES,
    can_transition_run,
    run_retry_decision,
)
from backend.app.core.workflow_runtime.domain.models import (
    WorkflowDefinition,
    WorkflowStatus as S,
    WorkflowTask,
    WorkflowTaskStatus,
)


def test_run_transitions() -> None:
    assert can_transition_run(S.CREATED, S.QUEUED)
    assert can_transition_run(S.RUNNING, S.INTERRUPTED)
    assert can_transition_run(S.RUNNING, S.QUEUED)  # recovery with nothing uncertain
    assert can_transition_run(S.FAILED, S.QUEUED)  # explicit retry only
    assert can_transition_run(S.INTERRUPTED, S.QUEUED)
    assert not can_transition_run(S.CREATED, S.RUNNING)
    assert not can_transition_run(S.FAILED, S.RUNNING)
    for final in FINAL_RUN_STATUSES:
        assert not any(can_transition_run(final, target) for target in S)


def test_run_retry_policy() -> None:
    assert not run_retry_decision(S.COMPLETED, uncertain_side_effect_steps=()).allowed
    assert not run_retry_decision(S.CANCELLED, uncertain_side_effect_steps=()).allowed
    plain = run_retry_decision(S.FAILED, uncertain_side_effect_steps=())
    assert plain.allowed and not plain.requires_acknowledgement
    risky = run_retry_decision(S.INTERRUPTED, uncertain_side_effect_steps=("send",))
    assert risky.requires_acknowledgement and "send" in risky.reason


def test_runs_snapshot_their_definition_version() -> None:
    step = WorkflowTask(task_id="a", name="A", configuration={"tool_name": "echo"}, status=WorkflowTaskStatus.COMPLETED)
    definition = WorkflowDefinition(name="flow", tasks=(step,), version=3)

    run = definition.new_run()

    assert (run.definition_id, run.definition_version) == (definition.definition_id, 3)
    assert run.tasks[0].status is WorkflowTaskStatus.PENDING
    assert run.tasks[0].workflow_id == run.workflow_id
    assert definition.tasks[0].workflow_id is None
