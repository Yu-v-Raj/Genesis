import assert from "node:assert/strict";
import test from "node:test";

import { MEMORY_KIND_TONES, statusPresentation } from "../lib/status.ts";

// Every status value declared in types/*.ts must have an explicit presentation.
const KNOWN = {
  execution: ["pending", "queued", "starting", "running", "completed", "failed", "cancelled", "interrupted"],
  agent: ["created", "initializing", "idle", "running", "waiting", "paused", "completed", "failed", "stopped"],
  workflow: ["created", "queued", "running", "paused", "completed", "failed", "cancelled", "interrupted"],
  workflowTask: ["pending", "ready", "running", "completed", "failed", "cancelled", "blocked", "interrupted"],
  tool: ["pending", "running", "completed", "failed", "rejected", "ready", "disabled"],
  service: ["online", "degraded", "offline"],
  connection: ["connecting", "connected", "disconnected"],
};

test("every known status has a deliberate label", () => {
  for (const [domain, statuses] of Object.entries(KNOWN)) {
    for (const status of statuses) {
      const { label } = statusPresentation(status);
      assert.notEqual(label, "Unknown", `${domain}:${status}`);
      assert.match(label, /^[A-Z]/, `${domain}:${status}`);
    }
  }
});

test("outcomes map to the expected tones", () => {
  assert.equal(statusPresentation("completed").tone, "success");
  assert.equal(statusPresentation("failed").tone, "danger");
  assert.equal(statusPresentation("interrupted").tone, "warning");
  assert.equal(statusPresentation("running").tone, "running");
  assert.equal(statusPresentation("running").active, true);
  assert.equal(statusPresentation("completed").active, false);
});

test("lookup ignores case and surrounding space", () => {
  assert.deepEqual(statusPresentation(" RUNNING "), statusPresentation("running"));
});

test("unknown statuses stay visible with a readable label and a neutral tone", () => {
  assert.deepEqual(statusPresentation("awaiting_approval"), { tone: "neutral", label: "Awaiting approval", active: false });
  assert.equal(statusPresentation(null).label, "Unknown");
  assert.equal(statusPresentation(undefined).tone, "neutral");
});

test("every memory kind has a tone", () => {
  assert.deepEqual(Object.keys(MEMORY_KIND_TONES).sort(), ["context", "fact", "note", "preference"]);
});
