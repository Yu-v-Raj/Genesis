import assert from "node:assert/strict";
import test from "node:test";

import type { Agent } from "../types/agents.ts";
import type { RealtimeEvent } from "../types/realtime.ts";
import type { ToolDefinition, ToolTask } from "../types/tools.ts";
import { agentsAllowing, availableFilters, buildArguments, declaredPermissions, filterTools, tasksForTool, testFieldsFor, toolLabel } from "../lib/tools.ts";
import { agentsUsingModel, modelCalls, redactSecrets, testFailureTitle } from "../lib/providers.ts";

function tool(overrides: Partial<ToolDefinition> = {}): ToolDefinition {
  return { name: "calculator", description: "Evaluate safe arithmetic.", version: "1.0.0", capabilities: ["calculation"], permissions: ["none"], enabled: true, side_effects: false, metadata: {}, ...overrides };
}

function agent(overrides: Partial<Agent> = {}): Agent {
  return {
    id: "a1", name: "Helper", description: "", type: "assistant", status: "idle", created_at: "2026-10-13T10:00:00Z", updated_at: "2026-10-13T10:00:00Z",
    metadata: {}, tags: [], llm_model: { provider: "gemini", model_name: "gemini-3.6-flash" }, allowed_tools: ["calculator"], instructions: "", ...overrides,
  };
}

function event(event_type: string, payload: RealtimeEvent["payload"], timestamp = "2026-10-14T10:00:00Z", id = `${event_type}-${timestamp}`): RealtimeEvent {
  return { id, timestamp, event_type, source: "test", payload };
}

test("tool search covers name, description and capabilities", () => {
  const tools = [tool(), tool({ name: "random_number", description: "Generate an integer.", capabilities: ["random_number"] }), tool({ name: "uuid", description: "Generate a random UUID.", capabilities: ["identifier_generation"] })];
  const names = (query: string) => filterTools(tools, { query, availability: "all", effects: "all" }).map((t) => t.name);
  assert.deepEqual(names("arith"), ["calculator"]);
  assert.deepEqual(names("Random number"), ["random_number"]);
  assert.deepEqual(names("identifier"), ["uuid"]);
  assert.deepEqual(names(""), ["calculator", "random_number", "uuid"]);
  assert.equal(toolLabel("random_number"), "Random number");
});

test("filters use the reported enabled and side-effect flags, and only appear when tools differ", () => {
  const tools = [tool(), tool({ name: "send_email", enabled: false, side_effects: true })];
  assert.deepEqual(filterTools(tools, { query: "", availability: "disabled", effects: "all" }).map((t) => t.name), ["send_email"]);
  assert.deepEqual(filterTools(tools, { query: "", availability: "all", effects: "none" }).map((t) => t.name), ["calculator"]);
  assert.deepEqual(availableFilters(tools), { availability: true, effects: true });
  assert.deepEqual(availableFilters([tool(), tool({ name: "echo" })]), { availability: false, effects: false });
});

test("eligibility comes from each Agent's allowed tools; the 'none' permission is not shown", () => {
  const agents = [agent({ id: "1" }), agent({ id: "2", allowed_tools: [] }), agent({ id: "3", allowed_tools: ["calculator", "echo"] })];
  assert.deepEqual(agentsAllowing(tool(), agents).map((a) => a.id), ["1", "3"]);
  assert.deepEqual(declaredPermissions(tool()), []);
  assert.deepEqual(declaredPermissions(tool({ permissions: ["none", "network"] })), ["network"]);
});

test("history is per tool", () => {
  const tasks = [{ tool_name: "calculator" }, { tool_name: "echo" }] as ToolTask[];
  assert.equal(tasksForTool(tasks, "echo").length, 1);
});

test("test-run arguments are validated before anything is sent", () => {
  const random = testFieldsFor("random_number")!;
  assert.deepEqual(buildArguments(random, { min: "1", max: "10" }), { arguments: { min: 1, max: 10 }, errors: null });
  assert.deepEqual(buildArguments(random, { min: "1.5", max: "" }).errors, { min: "Minimum must be a whole number.", max: "Maximum is required." });
  assert.deepEqual(buildArguments(testFieldsFor("delay")!, { seconds: "61" }).errors, { seconds: "Seconds must be at most 60." });
  assert.deepEqual(buildArguments(testFieldsFor("calculator")!, { expression: " 2 + 2 " }).arguments, { expression: "2 + 2" });
  assert.deepEqual(buildArguments(testFieldsFor("uuid")!, {}), { arguments: {}, errors: null });
  assert.equal(testFieldsFor("unknown_tool"), undefined);
});

test("model users are matched by provider and model", () => {
  const agents = [agent({ id: "1" }), agent({ id: "2", llm_model: { provider: "openai", model_name: "gpt-4.1-mini" } }), agent({ id: "3", llm_model: null })];
  assert.deepEqual(agentsUsingModel(agents, "gemini", "gemini-3.6-flash").map((a) => a.id), ["1"]);
});

test("model calls keep only safe fields and translate failures", () => {
  const calls = modelCalls([
    event("llm.completed", { provider: "gemini", model: "gemini-3.6-flash", duration_ms: 1922, usage: { total_tokens: 153 } }, "2026-10-14T10:00:00Z"),
    event("llm.failed", { provider: "gemini", model: "gemini-3.6-flash", duration_ms: 28153, error_type: "LLMProviderError" }, "2026-10-14T11:00:00Z"),
    event("llm.failed", { provider: "gemini", error_type: "Weird<script>" }, "2026-10-14T09:00:00Z"),
    event("llm.completed", { provider: "openai" }),
    event("llm.requested", { provider: "gemini" }),
  ], "gemini");
  assert.deepEqual(calls.map((c) => [c.ok, c.durationMs, c.totalTokens, c.reason]), [
    [false, 28153, null, "The provider returned an error."],
    [true, 1922, 153, null],
    [false, null, null, "The request failed."],
  ]);
});

test("credential-shaped text is redacted before display", () => {
  const leaked = "failed for key AIzaSyA1234567890abcdefghijklmnop and AQ.Ab8RN6abcdefghijklmnopqrstuv and sk-proj-abcdefghijklmnop and Bearer abcdefghijklmnopqrstu and https://x.test/?key=secret123";
  const clean = redactSecrets(leaked);
  assert.doesNotMatch(clean, /AIza[0-9A-Za-z]|AQ\.Ab8|sk-proj|abcdefghijklmnopqrstu|secret123/);
  assert.equal(redactSecrets("Gemini generation failed."), "Gemini generation failed.");
});

test("test failures get readable titles by status", () => {
  assert.match(testFailureTitle(503), /unavailable/);
  assert.match(testFailureTitle(504), /in time/);
  assert.match(testFailureTitle(undefined), /reach the server/);
  assert.equal(testFailureTitle(418), "The test request failed.");
});
