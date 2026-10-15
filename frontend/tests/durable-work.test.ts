import assert from "node:assert/strict";
import test from "node:test";

import type { Execution } from "../types/executions.ts";
import { describeTransition, executionLabel, isActive, retryPresentation, startedTools, statusText, unfinishedChats } from "../lib/durable-work.ts";

test("retry controls follow the server's decision exactly", () => {
  assert.equal(retryPresentation(null).visible, false);
  assert.equal(retryPresentation({ allowed: false, requires_acknowledgement: false, reason: "A completed execution cannot be retried." }).visible, false);

  const plain = retryPresentation({ allowed: true, requires_acknowledgement: false, reason: "Retrying starts a new attempt." });
  assert.deepEqual([plain.visible, plain.needsConfirmation, plain.label], [true, false, "Retry"]);

  const risky = retryPresentation({ allowed: true, requires_acknowledgement: true, reason: "may already have had external effects" });
  assert.deepEqual([risky.needsConfirmation, risky.label], [true, "Retry anyway"]);
  assert.match(risky.explanation, /external effects/);
});

test("statuses read as plain language and interruption is called out", () => {
  assert.equal(statusText("completed"), "Completed");
  assert.equal(statusText("failed"), "Failed");
  assert.match(statusText("interrupted"), /needs a decision/);
  assert.equal(isActive("running"), true);
  assert.equal(isActive("interrupted"), false);
});

test("timeline entries include the recorded reason", () => {
  assert.equal(
    describeTransition({ sequence: 5, from_status: "running", to_status: "interrupted", at: "2026-10-09T10:00:00Z", detail: "interrupted: worker stopped while the work was running" }),
    "Interrupted — needs a decision — interrupted: worker stopped while the work was running",
  );
  assert.equal(describeTransition({ sequence: 1, from_status: null, to_status: "pending", at: "x", detail: null }), "Pending");
});

function execution(overrides: Partial<Execution>): Execution {
  return {
    execution_id: "e1", agent_id: "a1", status: "completed", created_at: "2026-10-11T10:00:00Z", started_at: null, finished_at: null,
    updated_at: null, duration: null, result: null, error: null, error_category: null, current_step: null, attempt: 1, retry_of: null,
    retry: null, metadata: { kind: "chat", message: "Email the report", session_id: "s1" }, checkpoint: {}, ...overrides,
  };
}

test("chat executions are labelled by agent and message", () => {
  assert.equal(executionLabel(execution({}), "Math helper"), "Chat with Math helper: “Email the report”");
  assert.equal(executionLabel(execution({ metadata: { tool_name: "echo" } })), "Tool: echo");
  assert.deepEqual(startedTools(execution({ checkpoint: { tools_started: [{ name: "send_email", call_id: "c1", side_effects: true }] } })), ["send_email"]);
});

test("unfinished chats are scoped to the session and hidden once retried", () => {
  const interrupted = execution({ execution_id: "e1", status: "interrupted" });
  const otherSession = execution({ execution_id: "e2", status: "failed", metadata: { kind: "chat", message: "x", session_id: "s2" } });
  const done = execution({ execution_id: "e3", status: "completed" });
  assert.deepEqual(unfinishedChats([interrupted, otherSession, done], "s1").map((e) => e.execution_id), ["e1"]);
  const retry = execution({ execution_id: "e4", status: "completed", retry_of: "e1" });
  assert.deepEqual(unfinishedChats([retry, interrupted], "s1"), []);
  assert.deepEqual(unfinishedChats([interrupted], null), []);
});
