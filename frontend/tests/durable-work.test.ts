import assert from "node:assert/strict";
import test from "node:test";

import { describeTransition, isActive, retryPresentation, statusText } from "../lib/durable-work.ts";

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
  assert.equal(statusText("completed"), "Succeeded");
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
