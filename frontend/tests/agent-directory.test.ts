import assert from "node:assert/strict";
import test from "node:test";

import type { Agent, AgentStatus } from "../types/agents.ts";
import type { Execution } from "../types/executions.ts";
import {
  AGENT_STATUS_GROUPS, activeChatExecution, agentFilterCounts, agentInitials, filterAgents, liveTurnSteps, sortAgents,
} from "../lib/agent-directory.ts";

function agent(overrides: Partial<Agent> = {}): Agent {
  return {
    id: "a1", name: "Helper", description: "General-purpose assistant.", type: "assistant", status: "idle",
    created_at: "2026-10-13T10:00:00Z", updated_at: "2026-10-13T10:00:00Z", metadata: {}, tags: [],
    llm_model: { provider: "gemini", model_name: "gemini-3.6-flash" }, allowed_tools: ["calculator"], instructions: "", ...overrides,
  };
}

function execution(overrides: Partial<Execution> = {}): Execution {
  return {
    execution_id: "e1", agent_id: "a1", status: "running", created_at: "2026-10-13T11:00:00Z", started_at: null, finished_at: null,
    updated_at: null, duration: null, result: null, error: null, error_category: null, current_step: null, attempt: 1, retry_of: null,
    retry: null, metadata: { kind: "chat", message: "hi", session_id: "s1" }, checkpoint: {}, ...overrides,
  };
}

test("every lifecycle status belongs to exactly one filter group", () => {
  const all: AgentStatus[] = ["created", "initializing", "idle", "running", "waiting", "paused", "completed", "failed", "stopped"];
  assert.deepEqual(Object.values(AGENT_STATUS_GROUPS).flat().sort(), [...all].sort());
});

test("filters list only groups that have Agents, with counts", () => {
  const agents = [agent({ id: "1" }), agent({ id: "2", status: "stopped" }), agent({ id: "3" })];
  assert.deepEqual(agentFilterCounts(agents), [
    { value: "all", label: "All", count: 3 }, { value: "ready", label: "Ready", count: 2 }, { value: "stopped", label: "Stopped", count: 1 },
  ]);
});

test("search matches name, description, tags and model; filters combine", () => {
  const agents = [
    agent({ id: "1", name: "Researcher", tags: ["papers"] }),
    agent({ id: "2", name: "Writer", description: "Drafts blog posts", status: "stopped" }),
    agent({ id: "3", name: "Calc", llm_model: { provider: "openai", model_name: "gpt-4.1-mini" } }),
  ];
  const ids = (query: string, filter: Parameters<typeof filterAgents>[2] = "all") => filterAgents(agents, query, filter).map((a) => a.id);
  assert.deepEqual(ids("PAPERS"), ["1"]);
  assert.deepEqual(ids("blog"), ["2"]);
  assert.deepEqual(ids("openai"), ["3"]);
  assert.deepEqual(ids("", "stopped"), ["2"]);
  assert.deepEqual(ids("blog", "ready"), []);
  assert.deepEqual(ids("  "), ["1", "2", "3"]);
});

test("newest Agents come first", () => {
  const sorted = sortAgents([agent({ id: "old", created_at: "2026-01-01T00:00:00Z" }), agent({ id: "new", created_at: "2026-10-01T00:00:00Z" })]);
  assert.deepEqual(sorted.map((a) => a.id), ["new", "old"]);
});

test("initials handle punctuation and single words", () => {
  assert.equal(agentInitials("Gemini Verification Agent"), "GV");
  assert.equal(agentInitials("Isolation Test Agent."), "IT");
  assert.equal(agentInitials("calc"), "CA");
  assert.equal(agentInitials("!!!"), "A");
});

test("live steps come only from the real execution record", () => {
  assert.deepEqual(liveTurnSteps(null), [{ label: "Sending your message", state: "active" }]);
  assert.deepEqual(liveTurnSteps(execution({ status: "queued" })), [{ label: "Waiting to start", state: "active" }]);
  assert.deepEqual(liveTurnSteps(execution({ status: "running" })), [
    { label: "Started", state: "done" }, { label: "Working…", state: "active" },
  ]);
  // A started tool is "called", never claimed to have succeeded.
  assert.deepEqual(liveTurnSteps(execution({ status: "running", checkpoint: { tools_started: [{ name: "send_email", side_effects: true }] } })), [
    { label: "Started", state: "done" }, { label: "Called send email", state: "done" }, { label: "Working…", state: "active" },
  ]);
});

test("the active chat is matched by Agent, kind and session", () => {
  const runs = [
    execution({ execution_id: "other-agent", agent_id: "a2" }),
    execution({ execution_id: "done", status: "completed" }),
    execution({ execution_id: "tool-run", metadata: { tool_name: "echo" } }),
    execution({ execution_id: "other-session", metadata: { kind: "chat", session_id: "s2" } }),
    execution({ execution_id: "mine" }),
  ];
  assert.equal(activeChatExecution(runs, "a1", "s1")?.execution_id, "mine");
  assert.equal(activeChatExecution(runs, "a1", null)?.execution_id, "other-session");
  assert.equal(activeChatExecution(runs, "a3", null), null);
});

test("lifecycle actions match the existing rules", async () => {
  const { lifecycleActionsFor, canEditSettings } = await import("../lib/agent-directory.ts");
  assert.deepEqual(lifecycleActionsFor("created"), ["initialize", "stop"]);
  assert.deepEqual(lifecycleActionsFor("idle"), ["stop"]);
  assert.deepEqual(lifecycleActionsFor("initializing"), []);
  assert.deepEqual(lifecycleActionsFor("stopped"), ["delete"]);
  assert.equal(canEditSettings("idle"), true);
  assert.equal(canEditSettings("running"), false);
  assert.equal(canEditSettings("stopped"), false);
});
