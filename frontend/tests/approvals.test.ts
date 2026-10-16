import assert from "node:assert/strict";
import test from "node:test";

import {
  approveEffect,
  awaitedApproval,
  decisionSourceText,
  expiryText,
  rejectEffect,
  relatedLinks,
  requesterText,
  splitApprovals,
  stateSummary,
} from "../lib/approvals.ts";
import { statusPresentation } from "../lib/status.ts";
import type { Approval } from "../types/approvals.ts";

function approval(overrides: Partial<Approval> = {}): Approval {
  return {
    approval_id: "a1",
    state: "pending",
    caller: "agent",
    tool_name: "simulated_action",
    tool_description: "Simulates an external action.",
    tool_version: "1.0.0",
    reason: "This tool declares that it can affect things outside Genesis.",
    arguments: { note: "hi" },
    redacted_fields: [],
    subject: { agent_id: "ag1", agent_name: "Courier", execution_id: "ex1", workflow_id: null, workflow_name: null, step_id: null, step_name: null, attempt: null },
    created_at: "2026-10-16T10:00:00Z",
    expires_at: "2026-10-16T11:00:00Z",
    decided_at: null,
    decision_source: null,
    consumed_at: null,
    task_id: null,
    outcome: null,
    detail: null,
    can_decide: true,
    can_cancel: true,
    can_run: false,
    ...overrides,
  };
}

test("pending requests come first, oldest first; history newest decision first", () => {
  const { pending, history } = splitApprovals([
    approval({ approval_id: "p-new", created_at: "2026-10-16T10:05:00Z" }),
    approval({ approval_id: "done-old", state: "rejected", decided_at: "2026-10-16T09:00:00Z" }),
    approval({ approval_id: "p-old", created_at: "2026-10-16T10:01:00Z" }),
    approval({ approval_id: "done-new", state: "consumed", decided_at: "2026-10-16T10:30:00Z" }),
  ]);
  assert.deepEqual(pending.map((a) => a.approval_id), ["p-old", "p-new"]);
  assert.deepEqual(history.map((a) => a.approval_id), ["done-new", "done-old"]);
});

test("the requester comes from the real execution context", () => {
  assert.equal(requesterText(approval()), "Agent Courier, during a conversation");
  assert.equal(
    requesterText(approval({ caller: "workflow", subject: { ...approval().subject, agent_id: null, agent_name: null, workflow_id: "w", workflow_name: "Notify", step_id: "send", step_name: "Send", attempt: 2 } })),
    "Workflow Notify, step “Send” (attempt 2)",
  );
  assert.equal(requesterText(approval({ caller: "operator" })), "A test run from the Tools page");
  assert.equal(requesterText(approval({ subject: { ...approval().subject, agent_name: null } })), "Agent (no longer exists), during a conversation");
});

test("deciding is explained per caller, and approval never implies the call succeeded", () => {
  assert.match(approveEffect(approval()), /once, with exactly these arguments/);
  assert.match(rejectEffect(approval({ caller: "workflow" })), /blocked/);
  assert.equal(stateSummary(approval({ state: "approved" })), "Approved. The waiting work will use it shortly.");
  assert.equal(stateSummary(approval({ state: "consumed", outcome: "failed" })), "Approved and used: the call ran but the tool reported a failure.");
  assert.match(stateSummary(approval({ state: "consumed", outcome: "unknown" })), /not re-run/);
  assert.equal(stateSummary(approval({ state: "expired", detail: "No decision was recorded before the request expired." })), "No decision was recorded before the request expired.");
});

test("approval states have their own labels and Approved is not shown as success", () => {
  assert.equal(statusPresentation("approved").tone, "info");
  assert.equal(statusPresentation("consumed").label, "Used");
  assert.equal(statusPresentation("waiting_approval").label, "Waiting for approval");
  assert.equal(statusPresentation("expired").tone, "neutral");
});

test("expiry, decision source and links", () => {
  const now = new Date("2026-10-16T10:48:00Z");
  assert.equal(expiryText("2026-10-16T11:00:00Z", now), "Expires in 12 min");
  assert.equal(expiryText("2026-10-16T10:46:00Z", now), "Expired 2 min ago");
  assert.equal(decisionSourceText("local_operator_console"), "the Genesis console on this machine");
  assert.deepEqual(relatedLinks(approval()).map((link) => link.href), ["/agents?agent=ag1", "/monitoring?execution=ex1"]);
  assert.deepEqual(relatedLinks(approval({ caller: "operator", subject: { ...approval().subject, agent_id: null, execution_id: null } })).map((l) => l.href), ["/tools?tool=simulated_action"]);
});

test("a paused execution names the approval it waits on", () => {
  assert.equal(awaitedApproval({ awaiting: { token: "a1" }, step: "approval:x" }), "a1");
  assert.equal(awaitedApproval({}), null);
  assert.equal(awaitedApproval(null), null);
});
