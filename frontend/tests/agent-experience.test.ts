import assert from "node:assert/strict";
import test from "node:test";

import type { Agent, LLMModelOption, SessionMessage } from "../types/agents.ts";
import { agentReadiness, describeChatError, groupTurns, sessionLabel, toolStepLabel } from "../lib/agent-experience.ts";

const MODELS: LLMModelOption[] = [
  { provider: "gemini", model_name: "gemini-3.6-flash", capabilities: ["chat"], metadata: { configured: true } },
  { provider: "openai", model_name: "gpt-4.1-mini", capabilities: ["chat"], metadata: { configured: false } },
];

function agent(overrides: Partial<Agent> = {}): Agent {
  return {
    id: "a1",
    name: "Helper",
    description: "Helps",
    type: "assistant",
    status: "idle",
    created_at: "2026-10-09T00:00:00Z",
    updated_at: "2026-10-09T00:00:00Z",
    metadata: {},
    tags: [],
    llm_model: { provider: "gemini", model_name: "gemini-3.6-flash" },
    allowed_tools: ["calculator"],
    instructions: "",
    ...overrides,
  };
}

function message(overrides: Partial<SessionMessage>): SessionMessage {
  return { role: "user", content: "", interaction_id: "i1", tool_name: null, tool_status: null, tool_calls: [], ...overrides };
}

test("an idle agent with a configured model is ready", () => {
  assert.deepEqual(agentReadiness(agent(), MODELS).state, "ready");
});

test("readiness explains every blocking state", () => {
  assert.equal(agentReadiness(agent({ llm_model: null }), MODELS).state, "needs-model");
  assert.equal(agentReadiness(agent({ status: "created" }), MODELS).state, "not-initialized");
  assert.equal(agentReadiness(agent({ status: "running" }), MODELS).canChat, false);
  assert.equal(agentReadiness(agent({ status: "stopped" }), MODELS).state, "stopped");
  assert.equal(
    agentReadiness(agent({ llm_model: { provider: "gemini", model_name: "retired" } }), MODELS).state,
    "model-unavailable",
  );
  const unconfigured = agentReadiness(agent({ llm_model: { provider: "openai", model_name: "gpt-4.1-mini" } }), MODELS);
  assert.equal(unconfigured.state, "provider-unconfigured");
  assert.match(unconfigured.detail, /no API key for OpenAI/);
});

test("readiness does not guess about models before they load", () => {
  assert.equal(agentReadiness(agent({ llm_model: { provider: "x", model_name: "y" } }), null).state, "ready");
});

test("session messages are grouped into turns with tool steps and the final reply", () => {
  const turns = groupTurns([
    message({ role: "user", content: "Calculate 25 * 4" }),
    message({ role: "assistant", content: "", tool_calls: ["calculator", "echo"] }),
    message({ role: "tool", content: '{"success": true, "result": 100}', tool_name: "calculator", tool_status: "completed" }),
    message({ role: "tool", content: '{"success": false, "error": "Requested tool is not allowed."}', tool_name: "echo", tool_status: "rejected" }),
    message({ role: "assistant", content: "It is 100." }),
    message({ role: "user", content: "Thanks", interaction_id: "i2" }),
    message({ role: "assistant", content: "You're welcome.", interaction_id: "i2" }),
  ]);

  assert.equal(turns.length, 2);
  assert.equal(turns[0].user, "Calculate 25 * 4");
  assert.equal(turns[0].reply, "It is 100.");
  assert.deepEqual(turns[0].tools.map((step) => [step.name, step.status, step.result]), [
    ["calculator", "completed", 100],
    ["echo", "rejected", null],
  ]);
  assert.equal(toolStepLabel(turns[0].tools[1]), "Blocked — Not allowed for this Agent");
  assert.deepEqual([turns[1].user, turns[1].reply, turns[1].tools.length], ["Thanks", "You're welcome.", 0]);
});

test("messages without interaction ids still render one turn per user message", () => {
  const turns = groupTurns([
    message({ role: "user", content: "a", interaction_id: null }),
    message({ role: "assistant", content: "b", interaction_id: null }),
    message({ role: "user", content: "c", interaction_id: null }),
  ]);
  assert.deepEqual(turns.map((turn) => turn.user), ["a", "c"]);
});

test("chat errors become actionable explanations", () => {
  const missingKey = describeChatError(503, "Gemini is not configured: GEMINI_API_KEY is required.");
  assert.equal(missingKey.configure, true);
  assert.match(missingKey.message, /GEMINI_API_KEY/);
  assert.equal(describeChatError(undefined, "fetch failed").title, "Can't reach Genesis");
  assert.equal(describeChatError(409, "busy").configure, false);
  assert.match(describeChatError(504, "").message, /Try again/);
});

test("sessions get readable picker labels", () => {
  const now = new Date("2026-10-09T15:00:00");
  const base = { id: "s", agent_id: "a", created_at: "2026-10-09T10:00:00", message_count: 4 };
  assert.match(sessionLabel({ ...base, title: "Calculate 25 * 4", updated_at: "2026-10-08T12:00:00" }, now), /^Calculate 25 \* 4 · yesterday$/);
  assert.match(sessionLabel({ ...base, title: null, message_count: 0, updated_at: "2026-10-01T12:00:00" }, now), /^New conversation · /);
  assert.equal(sessionLabel({ ...base, title: "x", updated_at: "2026-10-06T12:00:00" }, now), "x · 3 days ago");
});
