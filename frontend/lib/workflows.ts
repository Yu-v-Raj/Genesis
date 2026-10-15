/**
 * Pure view logic for Workflows: step ordering from declared dependencies, run summaries,
 * the actions the server allows per status, search and filters, and builder validation.
 * Free of React for `node --test`. Nothing here decides anything the server enforces.
 */
import type { StoredWorkflowDefinition, Workflow, WorkflowStatus, WorkflowTask, WorkflowTaskStatus } from "@/types/workflows";

// ------------------------------------------------------------------ step structure

export interface StepLike {
  task_id: string;
  name: string;
  dependencies: string[];
}

/**
 * Group steps by dependency depth: stage 1 has no dependencies, stage n depends on
 * something in stage n-1. The server starts every step whose dependencies have all
 * completed, so steps in one stage may run at the same time. Declared order is kept
 * within a stage. Unknown dependency IDs are ignored here (the server rejects them).
 */
export function stepStages<T extends StepLike>(steps: readonly T[]): T[][] {
  const byId = new Map(steps.map((step) => [step.task_id, step]));
  const depth = new Map<string, number>();
  const visiting = new Set<string>();
  const depthOf = (step: T): number => {
    const known = depth.get(step.task_id);
    if (known !== undefined) return known;
    if (visiting.has(step.task_id)) return 0; // a cycle: the server never accepts one
    visiting.add(step.task_id);
    const parents = step.dependencies.map((id) => byId.get(id)).filter((parent): parent is T => parent !== undefined);
    const value = parents.length ? Math.max(...parents.map(depthOf)) + 1 : 0;
    visiting.delete(step.task_id);
    depth.set(step.task_id, value);
    return value;
  };
  const stages: T[][] = [];
  for (const step of steps) (stages[depthOf(step)] ??= []).push(step);
  return stages.filter(Boolean);
}

/** Readable names of a step's dependencies, in declared order. */
export function dependencyNames(step: StepLike, steps: readonly StepLike[]): string[] {
  return step.dependencies.map((id) => steps.find((other) => other.task_id === id)?.name ?? id);
}

export function stepToolName(step: { configuration: Record<string, unknown> }): string | null {
  return typeof step.configuration.tool_name === "string" ? step.configuration.tool_name : null;
}

export function stepArguments(step: { configuration: Record<string, unknown> }): Record<string, unknown> {
  const args = step.configuration.tool_arguments;
  return args && typeof args === "object" && !Array.isArray(args) ? (args as Record<string, unknown>) : {};
}

/** Distinct tools a workflow uses, in first-use order. */
export function toolsUsed(steps: readonly { configuration: Record<string, unknown> }[]): string[] {
  return [...new Set(steps.map(stepToolName).filter((name): name is string => name !== null))];
}

/** Seconds between start and finish, or `null` when either is missing (never 0 by default). */
export function stepDuration(step: Pick<WorkflowTask, "started_at" | "finished_at">): number | null {
  if (!step.started_at || !step.finished_at) return null;
  const seconds = (Date.parse(step.finished_at) - Date.parse(step.started_at)) / 1000;
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

// ------------------------------------------------------------------ runs

export interface RunProgress {
  total: number;
  completed: number;
  failed: number;
  running: number;
}

export function runProgress(run: Pick<Workflow, "tasks">): RunProgress {
  const count = (statuses: WorkflowTaskStatus[]) => run.tasks.filter((task) => statuses.includes(task.status)).length;
  return { total: run.tasks.length, completed: count(["completed"]), failed: count(["failed", "interrupted"]), running: count(["running", "ready"]) };
}

/** Runs of one saved workflow, newest first. */
export function runsOf(runs: readonly Workflow[], definitionId: string): Workflow[] {
  return runs.filter((run) => run.definition_id === definitionId).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

export type RunAction = "start" | "pause" | "resume" | "cancel" | "retry" | "delete";

/**
 * Actions offered for a run status, mirroring the server's rules
 * (workflow_runtime/domain/lifecycle.py and WorkflowManager). The server still decides:
 * retry also needs `run.retry.allowed`, and any request can be refused.
 */
export function runActions(status: WorkflowStatus): RunAction[] {
  switch (status) {
    case "created": return ["start", "cancel", "delete"];
    case "queued": return ["cancel"];
    case "running": return ["pause", "cancel"];
    case "paused": return ["resume", "cancel"];
    case "interrupted": return ["retry", "cancel", "delete"];
    case "failed": return ["retry", "delete"];
    case "completed":
    case "cancelled": return ["delete"];
  }
}

export function isRunActive(status: WorkflowStatus): boolean {
  return status === "queued" || status === "running" || status === "paused";
}

export type RunFilter = "all" | "active" | "attention" | "completed" | "cancelled" | "not_started";

export const RUN_FILTERS: readonly { value: RunFilter; label: string; statuses: readonly WorkflowStatus[] }[] = [
  { value: "all", label: "All runs", statuses: [] },
  { value: "active", label: "In progress", statuses: ["queued", "running", "paused"] },
  { value: "attention", label: "Needs attention", statuses: ["failed", "interrupted"] },
  { value: "completed", label: "Completed", statuses: ["completed"] },
  { value: "not_started", label: "Not started", statuses: ["created"] },
  { value: "cancelled", label: "Cancelled", statuses: ["cancelled"] },
];

export function filterRuns(runs: readonly Workflow[], query: string, filter: RunFilter): Workflow[] {
  const statuses = RUN_FILTERS.find((item) => item.value === filter)?.statuses ?? [];
  const needle = query.trim().toLowerCase();
  return runs
    .filter((run) => (filter === "all" || statuses.includes(run.status)) && (!needle || `${run.name} ${run.description} ${run.workflow_id}`.toLowerCase().includes(needle)))
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
}

export function filterDefinitions(definitions: readonly StoredWorkflowDefinition[], query: string): StoredWorkflowDefinition[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [...definitions];
  return definitions.filter((definition) =>
    [definition.name, definition.description, ...definition.tasks.map((task) => task.name), ...toolsUsed(definition.tasks)].join(" ").toLowerCase().includes(needle));
}

// ------------------------------------------------------------------ builder

export interface DraftStep {
  key: string;
  task_id: string;
  name: string;
  tool_name: string;
  argumentsText: string;
  dependencies: string[];
}

export interface DraftErrors {
  name?: string;
  steps: Record<string, Partial<Record<"task_id" | "name" | "tool_name" | "arguments", string>>>;
}

export function parseArguments(text: string): Record<string, unknown> | null {
  if (!text.trim()) return {};
  try {
    const parsed: unknown = JSON.parse(text);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** Validate before sending; the server repeats every check (tools, dependencies, cycles). */
export function validateBuilder(name: string, steps: readonly DraftStep[], knownTools: readonly string[]): DraftErrors {
  const errors: DraftErrors = { steps: {} };
  if (!name.trim()) errors.name = "Give this workflow a name.";
  const seen = new Set<string>();
  steps.forEach((step, index) => {
    const stepErrors: DraftErrors["steps"][string] = {};
    const id = step.task_id.trim();
    if (!id) stepErrors.task_id = "Give the step an ID.";
    else if (seen.has(id)) stepErrors.task_id = "Step IDs must be unique.";
    seen.add(id);
    if (!step.name.trim()) stepErrors.name = "Give the step a name.";
    if (!step.tool_name) stepErrors.tool_name = "Choose a tool.";
    else if (knownTools.length && !knownTools.includes(step.tool_name)) stepErrors.tool_name = "This tool isn't registered on the server.";
    if (parseArguments(step.argumentsText) === null) stepErrors.arguments = "Arguments must be a JSON object, for example {\"message\": \"hi\"}.";
    const earlier = new Set(steps.slice(0, index).map((other) => other.task_id.trim()));
    if (step.dependencies.some((dependency) => !earlier.has(dependency))) stepErrors.task_id ??= "A step can only wait for steps listed before it.";
    if (Object.keys(stepErrors).length) errors.steps[step.key] = stepErrors;
  });
  return errors;
}

export function hasErrors(errors: DraftErrors): boolean {
  return Boolean(errors.name) || Object.keys(errors.steps).length > 0;
}
