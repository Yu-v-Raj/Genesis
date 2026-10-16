import assert from "node:assert/strict";
import test from "node:test";

import type { ModelCall, RuntimeEvent, WorkflowTransition } from "../types/operations.ts";
import { describeEvent, eventCategory } from "../lib/activity.ts";
import { errorCategoryLabel, operationsQuery } from "../lib/operations.ts";
import {
  DURABLE_EVENT_FILTERS, asRealtimeEvent, attemptsOf, describeWorkflowTransition, eventFilterType, eventsSearch, isDurableEventType, mergeById,
  mergeEvents, summarizeModelCalls, truncationNote,
} from "../lib/traces.ts";

function change(overrides: Partial<WorkflowTransition>): WorkflowTransition {
  return { sequence: 1, step_id: null, attempt: 1, from_status: null, to_status: "created", at: "2026-10-16T10:00:00Z", worker: null, detail: null, ...overrides };
}

function stored(sequence: number, overrides: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    sequence, event_id: `e${sequence}`, event_type: "execution.completed", source: "test", occurred_at: "2026-10-16T10:00:00Z", payload: {},
    execution_id: null, interaction_id: null, agent_id: null, workflow_id: null, step_id: null, tool_task_id: null, approval_id: null, ...overrides,
  };
}

test("workflow timeline entries read as plain sentences", () => {
  const names = { send: "Send notice" };
  assert.equal(describeWorkflowTransition(change({})), "Run created");
  assert.equal(describeWorkflowTransition(change({ from_status: "queued", to_status: "running", worker: "host-1:42" })), "Run claimed by worker host-1:42");
  assert.equal(describeWorkflowTransition(change({ from_status: "waiting_approval", to_status: "queued" })), "Run queued again after an approval decision");
  assert.equal(describeWorkflowTransition(change({ from_status: "failed", to_status: "queued", attempt: 2 })), "Run queued for attempt 2");
  assert.equal(describeWorkflowTransition(change({ from_status: "created", to_status: "queued" })), "Run queued");
  assert.equal(describeWorkflowTransition(change({ step_id: "send", from_status: "running", to_status: "waiting_approval" }), names), "Step “Send notice” is waiting for approval");
  assert.equal(describeWorkflowTransition(change({ step_id: "send", from_status: "waiting_approval", to_status: "pending" }), names), "Step “Send notice” was approved and will run");
  assert.equal(describeWorkflowTransition(change({ step_id: "send", from_status: "running", to_status: "pending" }), names), "Step “Send notice” will run again (its run was recovered)");
  assert.equal(describeWorkflowTransition(change({ step_id: "other", from_status: "running", to_status: "interrupted" }), names), "Step “other” was interrupted; its outcome is unknown");
  assert.deepEqual(attemptsOf([change({ attempt: 2 }), change({ attempt: 1 }), change({ attempt: 2 })]), [1, 2]);
});

test("model call summaries add up timing and tokens, and say when usage is unknown", () => {
  const call = (overrides: Partial<ModelCall>): ModelCall => ({
    sequence: 1, at: "2026-10-16T10:00:00Z", outcome: "completed", provider: "openai", model: "m", duration_ms: 1500, input_tokens: 10, output_tokens: 5, total_tokens: 15, error_type: null, ...overrides,
  });
  assert.deepEqual(summarizeModelCalls([call({}), call({ outcome: "failed", total_tokens: null, duration_ms: 500, error_type: "TimeoutError" })]), { count: 2, failed: 1, totalTokens: 15, totalSeconds: 2 });
  assert.equal(summarizeModelCalls([call({ total_tokens: null })]).totalTokens, null);
  assert.deepEqual(summarizeModelCalls([]), { count: 0, failed: 0, totalTokens: null, totalSeconds: 0 });
});

test("a cut trace says which lists were cut", () => {
  assert.equal(truncationNote({ tool_tasks: false, approvals: false, events: false }), null);
  assert.equal(truncationNote({ tool_tasks: true, approvals: false, events: true }), "This trace is long, so only the most recent tool runs and events are shown.");
});

test("stored event pages merge without duplicates, newest first", () => {
  const merged = mergeEvents([stored(5), stored(3)], [stored(4), stored(3, { event_type: "execution.failed" })]);
  assert.deepEqual(merged.map((event) => event.sequence), [5, 4, 3]);
  assert.equal(merged[2].event_type, "execution.failed");
  const live = asRealtimeEvent(stored(7, { event_type: "workflow.task.completed", payload: { task_id: "send" } }));
  assert.deepEqual([live.id, live.event_type], ["e7", "workflow.task.completed"]);
});

test("records merge by id and stay newest first", () => {
  const rows = mergeById([{ id: "a", at: "2026-10-16T10:00:00Z" }], [{ id: "b", at: "2026-10-16T11:00:00Z" }, { id: "a", at: "2026-10-16T10:00:00Z" }], (row) => row.id, (row) => row.at);
  assert.deepEqual(rows.map((row) => row.id), ["b", "a"]);
});

test("event filters map to server-side type filters, and only stored types trigger refreshes", () => {
  assert.equal(eventFilterType("all"), null);
  assert.equal(eventFilterType("workflow"), "workflow.");
  assert.equal(eventFilterType("refusal"), "tool.rejected");
  assert.equal(eventFilterType("unknown"), null);
  assert.equal(new Set(DURABLE_EVENT_FILTERS.map((filter) => filter.value)).size, DURABLE_EVENT_FILTERS.length);
  for (const type of ["execution.completed", "workflow.task.ready", "task.created", "approval.requested", "tool.rejected", "llm.completed", "llm.failed", "llm.retrying"]) assert.equal(isDurableEventType(type), true, type);
  for (const type of ["log.created", "system.heartbeat", "llm.requested", "agent.created", "memory.added"]) assert.equal(isDurableEventType(type), false, type);
});

test("event queries leave out empty values", () => {
  assert.equal(eventsSearch({}), "");
  assert.equal(eventsSearch({ limit: 50, event_type: "workflow.", before_sequence: null, execution_id: "" }), "?limit=50&event_type=workflow.");
  assert.equal(eventsSearch({ workflow_id: "w 1" }), "?workflow_id=w+1");
});

test("workflow and approval events have readable descriptions", () => {
  const event = (event_type: string, payload: Record<string, unknown>) => ({ id: event_type, timestamp: "2026-10-16T10:00:00Z", event_type, source: "t", payload: payload as never });
  assert.equal(describeEvent(event("workflow.task.waiting_approval", { task_id: "send" })), "Workflow step “send” is waiting for approval");
  assert.equal(describeEvent(event("workflow.waiting_approval", {})), "Workflow run waiting for an approval decision");
  assert.equal(describeEvent(event("workflow.definition.created", {})), "Workflow saved");
  assert.equal(describeEvent(event("approval.requested", { tool_name: "simulated_action" })), "Approval requested · simulated_action");
  assert.equal(describeEvent(event("approval.consumed", { tool_name: "simulated_action" })), "Approved call started · simulated_action");
  assert.equal(eventCategory("approval.rejected"), "approval");
  assert.equal(describeEvent(event("llm.retrying", { model: "gpt", attempt: 1 })), "gpt request failed temporarily (attempt 1); retrying");
  assert.equal(describeEvent(event("tool.rejected", { tool_name: "simulated_action", reason: "approval_required" })), "simulated_action held for the operator's approval");
  assert.equal(describeEvent(event("tool.rejected", { tool_name: "echo", reason: "tool_not_granted" })), "echo refused by tool policy (tool not granted)");
});

test("model failure categories have readable labels", () => {
  assert.equal(errorCategoryLabel("rate_limited"), "Rate limited by the model provider");
  assert.equal(errorCategoryLabel("provider_unavailable"), "Model provider temporarily unavailable");
  assert.equal(errorCategoryLabel("invalid_response"), "Unreadable model response");
});

test("the Operations URL carries the selected workflow run", () => {
  assert.equal(operationsQuery({ tab: "workflows", run: "r1" }), "?tab=workflows&run=r1");
  assert.equal(operationsQuery({ tab: "executions", run: null }), "");
});
