import assert from "node:assert/strict";
import test from "node:test";

import type { Execution, ExecutionStatus } from "../types/executions.ts";
import type { LLMModelOption } from "../types/agents.ts";
import type { RealtimeEvent } from "../types/realtime.ts";
import { describeEvent, eventCategory, isRoutineEvent } from "../lib/activity.ts";
import {
  EXECUTION_LIST_LIMIT, STATUS_GROUPS, countLabel, errorCategoryExplanation, errorCategoryLabel, executionKind, filterExecutions, filtersFromParams, formatDuration,
  hasActiveFilters, operationsQuery, relativeTime, summarizeAgents, summarizeExecutions,
} from "../lib/operations.ts";
import { providerReadiness } from "../lib/providers.ts";

const NOW = new Date("2026-10-13T12:00:00Z");

function execution(overrides: Partial<Execution> = {}): Execution {
  return {
    execution_id: "e1", agent_id: "a1", status: "completed", created_at: "2026-10-13T11:00:00Z", started_at: null, finished_at: null,
    updated_at: null, duration: null, result: null, error: null, error_category: null, current_step: null, attempt: 1, retry_of: null,
    retry: null, metadata: { kind: "chat", message: "Summarize the report", session_id: "s1" }, checkpoint: {}, ...overrides,
  };
}

function event(event_type: string, payload: RealtimeEvent["payload"], timestamp = "2026-10-13T11:00:00Z"): RealtimeEvent {
  return { id: `${event_type}-${timestamp}`, timestamp, event_type, source: "test", payload };
}

test("status groups cover every execution status exactly once", () => {
  const all: ExecutionStatus[] = ["pending", "queued", "starting", "running", "completed", "failed", "cancelled", "interrupted", "waiting_approval"];
  const grouped = Object.values(STATUS_GROUPS).flat();
  assert.deepEqual([...grouped].sort(), [...all].sort());
});

test("filters combine status group, agent, kind and text search", () => {
  const rows = [
    execution({ execution_id: "e1", status: "failed", agent_id: "a1" }),
    execution({ execution_id: "e2", status: "interrupted", agent_id: "a2" }),
    execution({ execution_id: "e3", status: "completed", agent_id: "a1", metadata: { tool_name: "echo" } }),
    execution({ execution_id: "e4", status: "running", agent_id: "a1", metadata: { kind: "chat", message: "Plan the launch" } }),
  ];
  const names = { a1: "Researcher", a2: "Writer" };
  const ids = (filters: Parameters<typeof filterExecutions>[1]) => filterExecutions(rows, filters, names).map((row) => row.execution_id);

  assert.deepEqual(ids({ status: "attention", agentId: null, kind: null, query: "" }), ["e1", "e2"]);
  assert.deepEqual(ids({ status: "attention", agentId: "a2", kind: null, query: "" }), ["e2"]);
  assert.deepEqual(ids({ status: "all", agentId: null, kind: "tool", query: "" }), ["e3"]);
  assert.deepEqual(ids({ status: "all", agentId: null, kind: null, query: "launch" }), ["e4"]);
  assert.deepEqual(ids({ status: "all", agentId: null, kind: null, query: "writer" }), ["e2"]);
  assert.equal(executionKind(rows[2]), "tool");
});

test("URL state round-trips and ignores unknown values", () => {
  const query = operationsQuery({ status: "attention", agentId: "a1", kind: "chat", query: " report ", execution: "e9" });
  assert.equal(query, "?status=attention&agent=a1&kind=chat&q=report&execution=e9");
  const parsed = filtersFromParams(new URLSearchParams(query));
  assert.deepEqual(parsed, { status: "attention", agentId: "a1", kind: "chat", query: "report" });
  assert.equal(hasActiveFilters(parsed), true);
  assert.equal(filtersFromParams(new URLSearchParams("?status=bogus")).status, "all");
  assert.equal(operationsQuery({ status: "all", tab: "executions" }), "");
  assert.equal(operationsQuery({ tab: "logs" }), "?tab=logs");
});

test("24-hour summary counts only recent executions and flags a truncated list", () => {
  const rows = [
    execution({ status: "completed", created_at: "2026-10-13T11:00:00Z" }),
    execution({ status: "failed", created_at: "2026-10-13T10:00:00Z" }),
    execution({ status: "interrupted", created_at: "2026-10-13T09:00:00Z" }),
    execution({ status: "running", created_at: "2026-10-13T08:00:00Z" }),
    execution({ status: "failed", created_at: "2026-10-11T08:00:00Z" }),
  ];
  assert.deepEqual(summarizeExecutions(rows, NOW), { last24h: 4, completed24h: 1, attention24h: 2, active: 1, capped: false });

  const full = Array.from({ length: EXECUTION_LIST_LIMIT }, () => execution({ created_at: "2026-10-13T11:30:00Z" }));
  const summary = summarizeExecutions(full, NOW);
  assert.equal(summary.capped, true);
  assert.equal(countLabel(summary.last24h, summary.capped), "200+");
  assert.equal(summarizeExecutions([], NOW).capped, false);
});

test("agent summary separates ready, working and other Agents", () => {
  assert.deepEqual(summarizeAgents(["idle", "idle", "running", "paused", "created"]), { total: 5, ready: 2, working: 1, other: 2 });
});

test("relative times and durations read naturally", () => {
  assert.equal(relativeTime("2026-10-13T11:59:50Z", NOW), "just now");
  assert.equal(relativeTime("2026-10-13T11:55:00Z", NOW), "5 min ago");
  assert.equal(relativeTime("2026-10-13T09:00:00Z", NOW), "3 h ago");
  assert.equal(relativeTime("2026-10-12T12:00:00Z", NOW), "yesterday");
  assert.equal(relativeTime(null, NOW), "—");
  assert.equal(formatDuration(0.25), "250 ms");
  assert.equal(formatDuration(1.94), "1.9 s");
  assert.equal(formatDuration(null), "—");
});

const MODELS: LLMModelOption[] = [
  { provider: "gemini", model_name: "gemini-3.6-flash", capabilities: ["chat"], metadata: { configured: true } },
  { provider: "openai", model_name: "gpt-4.1-mini", capabilities: ["chat"], metadata: { configured: false } },
];

test("a configured provider without a recorded response is never shown as working", () => {
  const [gemini, openai] = providerReadiness(MODELS, []);
  assert.deepEqual([gemini.label, gemini.state, gemini.evidence.kind], ["Gemini", "configured", "none"]);
  assert.deepEqual([openai.label, openai.state], ["OpenAI", "not_configured"]);
});

test("provider state follows the most recent recorded outcome", () => {
  const ok = event("llm.completed", { provider: "gemini", model: "gemini-3.6-flash" }, "2026-10-13T11:00:00Z");
  const failed = event("llm.failed", { provider: "gemini", model: "gemini-3.6-flash", error_type: "LLMConfigurationError" }, "2026-10-13T11:30:00Z");
  assert.equal(providerReadiness(MODELS, [ok])[0].state, "provider_responding");

  const [gemini] = providerReadiness(MODELS, [ok, failed]);
  assert.equal(gemini.state, "provider_failing");
  assert.ok(gemini.evidence.kind === "failure" && /API key/.test(gemini.evidence.reason));

  const recovered = event("llm.completed", { provider: "gemini" }, "2026-10-13T11:45:00Z");
  assert.equal(providerReadiness(MODELS, [failed, recovered])[0].state, "provider_responding");
});

test("unknown failure types are not echoed back to the UI", () => {
  const failed = event("llm.failed", { provider: "gemini", error_type: "<script>alert(1)</script>" });
  const [gemini] = providerReadiness(MODELS, [failed]);
  assert.ok(gemini.evidence.kind === "failure" && gemini.evidence.reason === "The request failed.");
});

test("a provider that is not configured stays 'not configured' even with an old success", () => {
  const ok = event("llm.completed", { provider: "openai" });
  assert.equal(providerReadiness(MODELS, [ok]).find((p) => p.provider === "openai")?.state, "not_configured");
});

test("events read as sentences with Agent names", () => {
  const names = { a1: "Researcher" };
  assert.equal(describeEvent(event("execution.completed", { kind: "chat", agent_id: "a1" }), names), "Chat turn completed · Researcher");
  assert.equal(describeEvent(event("execution.progress", { kind: "chat", step: "tool:calculator" })), "Chat turn in progress (tool:calculator)");
  assert.equal(describeEvent(event("agent.status_changed", { agent_id: "a1", status: "idle" }), names), "Researcher is now idle");
  assert.equal(describeEvent(event("llm.completed", { model: "gemini-3.6-flash", duration_ms: 1922 })), "gemini-3.6-flash responded in 1.9 s");
  assert.equal(describeEvent(event("service.registered", { service: "event_bus" })), "Service registered: event_bus");
  assert.equal(describeEvent(event("something.new_thing", {})), "Something new thing");
  assert.equal(eventCategory("llm.failed"), "model");
  assert.equal(isRoutineEvent("system.heartbeat"), true);
  assert.equal(isRoutineEvent("agent.created"), false);
});

test("error categories read as plain language", () => {
  assert.equal(errorCategoryLabel("provider_error"), "Model provider error");
  assert.equal(errorCategoryLabel("interrupted"), "Interrupted by a restart");
  assert.equal(errorCategoryLabel("new_category"), "new category");
  assert.equal(errorCategoryLabel(null), null);
});

test("a policy refusal reads differently from a tool failure, and other labels are unchanged", () => {
  assert.equal(errorCategoryLabel("tool_denied"), "Refused by tool policy");
  assert.match(errorCategoryExplanation("tool_denied") ?? "", /before the tool ran, so nothing was executed/);
  assert.doesNotMatch(errorCategoryExplanation("tool_denied") ?? "", /approval/i);  // a refusal isn't a rejected approval
  assert.equal(errorCategoryLabel("tool_failed"), "Tool failed");
  assert.match(errorCategoryExplanation("tool_failed") ?? "", /started running/);
  assert.equal(errorCategoryExplanation("timeout"), null);
  assert.equal(errorCategoryLabel("provider_error"), "Model provider error");
  assert.equal(errorCategoryLabel("interrupted"), "Interrupted by a restart");
  assert.equal(errorCategoryLabel("something_new"), "something new");
  assert.equal(errorCategoryLabel(null), null);
});
