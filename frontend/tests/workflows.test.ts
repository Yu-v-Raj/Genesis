import assert from "node:assert/strict";
import test from "node:test";

import type { StoredWorkflowDefinition, Workflow, WorkflowStatus, WorkflowTask } from "../types/workflows.ts";
import {
  dependencyNames, filterDefinitions, filterRuns, hasErrors, parseArguments, runActions, runProgress, runsOf, stepDuration, stepStages, toolsUsed, validateBuilder,
} from "../lib/workflows.ts";

const step = (task_id: string, dependencies: string[] = [], tool = "echo") => ({ task_id, name: `Step ${task_id}`, dependencies, configuration: { tool_name: tool, tool_arguments: {} } });

function task(overrides: Partial<WorkflowTask>): WorkflowTask {
  return { task_id: "a", workflow_id: "w1", name: "A", action: "tool", configuration: { tool_name: "echo", tool_arguments: {} }, dependencies: [], status: "pending", created_at: "2026-10-16T10:00:00Z", started_at: null, finished_at: null, result: null, error: null, metadata: {}, ...overrides };
}

function run(overrides: Partial<Workflow>): Workflow {
  return { workflow_id: "w1", name: "Report", description: "", metadata: {}, status: "completed", created_at: "2026-10-16T10:00:00Z", updated_at: "2026-10-16T10:00:00Z", tasks: [], definition_id: "d1", definition_version: 1, attempt: 1, error: null, retry: null, ...overrides };
}

test("stages follow declared dependencies, keeping declared order within a stage", () => {
  const steps = [step("fetch"), step("check"), step("sum", ["fetch", "check"]), step("report", ["sum"]), step("notify", ["fetch"])];
  assert.deepEqual(stepStages(steps).map((stage) => stage.map((s) => s.task_id)), [["fetch", "check"], ["sum", "notify"], ["report"]]);
  assert.deepEqual(dependencyNames(steps[2], steps), ["Step fetch", "Step check"]);
});

test("a purely sequential workflow stays sequential, and no edges are invented", () => {
  assert.deepEqual(stepStages([step("a"), step("b", ["a"]), step("c", ["b"])]).map((s) => s.length), [1, 1, 1]);
  assert.deepEqual(stepStages([step("a"), step("b")]).map((s) => s.length), [2]); // no dependencies declared
  assert.deepEqual(stepStages([step("a", ["missing"])]).map((s) => s.length), [1]);
});

test("tools are listed once in first-use order", () => {
  assert.deepEqual(toolsUsed([step("a", [], "echo"), step("b", [], "calculator"), step("c", [], "echo")]), ["echo", "calculator"]);
});

test("a missing start or finish never becomes a zero duration", () => {
  assert.equal(stepDuration(task({ started_at: "2026-10-16T10:00:00Z", finished_at: "2026-10-16T10:00:02.5Z" })), 2.5);
  assert.equal(stepDuration(task({ started_at: "2026-10-16T10:00:00Z" })), null);
  assert.equal(stepDuration(task({ finished_at: "2026-10-16T10:00:00Z" })), null);
});

test("progress counts come from the run's own steps", () => {
  const progress = runProgress(run({ tasks: [task({ status: "completed" }), task({ status: "failed" }), task({ status: "blocked" }), task({ status: "running" })] }));
  assert.deepEqual(progress, { total: 4, completed: 1, failed: 1, running: 1 });
});

test("actions mirror the server's lifecycle rules for every status", () => {
  const expected: Record<WorkflowStatus, string[]> = {
    created: ["start", "cancel", "delete"], queued: ["cancel"], running: ["pause", "cancel"], paused: ["resume", "cancel"],
    interrupted: ["retry", "cancel", "delete"], failed: ["retry", "delete"], completed: ["delete"], cancelled: ["delete"],
  };
  for (const [status, actions] of Object.entries(expected)) assert.deepEqual(runActions(status as WorkflowStatus), actions, status);
});

test("runs are matched to their saved workflow and filtered by status group and text", () => {
  const runs = [run({ workflow_id: "1", status: "failed", updated_at: "2026-10-16T09:00:00Z" }), run({ workflow_id: "2", status: "running", definition_id: "d2", name: "Sync" }), run({ workflow_id: "3", status: "interrupted", created_at: "2026-10-16T11:00:00Z" })];
  assert.deepEqual(runsOf(runs, "d1").map((r) => r.workflow_id), ["3", "1"]);
  assert.deepEqual(filterRuns(runs, "", "attention").map((r) => r.workflow_id).sort(), ["1", "3"]);
  assert.deepEqual(filterRuns(runs, "sync", "all").map((r) => r.workflow_id), ["2"]);
});

test("saved workflows are searchable by name, step names and tools", () => {
  const definitions = [{ definition_id: "d1", version: 1, name: "Daily report", description: "", metadata: {}, created_at: "", tasks: [{ ...step("a", [], "calculator"), action: "tool" }] }] as StoredWorkflowDefinition[];
  assert.equal(filterDefinitions(definitions, "calculator").length, 1);
  assert.equal(filterDefinitions(definitions, "step a").length, 1);
  assert.equal(filterDefinitions(definitions, "zzz").length, 0);
});

test("the builder catches problems before anything is sent", () => {
  const ok = validateBuilder("Report", [{ key: "1", task_id: "a", name: "A", tool_name: "echo", argumentsText: '{"message":"hi"}', dependencies: [] }, { key: "2", task_id: "b", name: "B", tool_name: "calculator", argumentsText: "", dependencies: ["a"] }], ["echo", "calculator"]);
  assert.equal(hasErrors(ok), false);

  const bad = validateBuilder(" ", [
    { key: "1", task_id: "a", name: "", tool_name: "", argumentsText: "[1]", dependencies: [] },
    { key: "2", task_id: "a", name: "B", tool_name: "send_email", argumentsText: "{}", dependencies: [] },
    { key: "3", task_id: "c", name: "C", tool_name: "echo", argumentsText: "{}", dependencies: ["later"] },
  ], ["echo"]);
  assert.equal(bad.name, "Give this workflow a name.");
  assert.deepEqual(Object.keys(bad.steps["1"]).sort(), ["arguments", "name", "tool_name"]);
  assert.equal(bad.steps["2"].task_id, "Step IDs must be unique.");
  assert.equal(bad.steps["2"].tool_name, "This tool isn't registered on the server.");
  assert.match(bad.steps["3"].task_id ?? "", /before it/);
  assert.equal(parseArguments("not json"), null);
  assert.deepEqual(parseArguments(""), {});
});
