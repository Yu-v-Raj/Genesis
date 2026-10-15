/**
 * Pure view logic for the Agents directory and workspace: search, status groups, ordering
 * and the per-turn activity of a conversation. Free of React for `node --test`.
 */
import type { Agent, AgentStatus } from "@/types/agents";
import type { Execution } from "@/types/executions";
import { modelLabel } from "./agent-experience.ts";

export type AgentFilter = "all" | "ready" | "working" | "setup" | "stopped" | "other";

/** Groups over the real lifecycle statuses; every status belongs to exactly one group. */
export const AGENT_STATUS_GROUPS: Readonly<Record<Exclude<AgentFilter, "all">, readonly AgentStatus[]>> = {
  ready: ["idle"],
  working: ["running", "initializing", "waiting"],
  setup: ["created"],
  stopped: ["stopped"],
  other: ["paused", "completed", "failed"],
};

export const AGENT_FILTER_LABELS: Readonly<Record<AgentFilter, string>> = {
  all: "All",
  ready: "Ready",
  working: "Working",
  setup: "Needs setup",
  stopped: "Stopped",
  other: "Other",
};

export function agentFilterOf(status: AgentStatus): Exclude<AgentFilter, "all"> {
  const entry = Object.entries(AGENT_STATUS_GROUPS).find(([, statuses]) => statuses.includes(status));
  return (entry?.[0] as Exclude<AgentFilter, "all"> | undefined) ?? "other";
}

/** Filters worth offering: "All" plus every group that currently has at least one Agent. */
export function agentFilterCounts(agents: readonly Agent[]): { value: AgentFilter; label: string; count: number }[] {
  const counts = new Map<AgentFilter, number>();
  for (const agent of agents) {
    const group = agentFilterOf(agent.status);
    counts.set(group, (counts.get(group) ?? 0) + 1);
  }
  const groups = (Object.keys(AGENT_STATUS_GROUPS) as Exclude<AgentFilter, "all">[]).filter((group) => counts.has(group));
  return [{ value: "all", label: AGENT_FILTER_LABELS.all, count: agents.length }, ...groups.map((group) => ({ value: group, label: AGENT_FILTER_LABELS[group], count: counts.get(group) ?? 0 }))];
}

/** Case-insensitive search over the fields a person would recognise an Agent by. */
export function filterAgents(agents: readonly Agent[], query: string, filter: AgentFilter): Agent[] {
  const needle = query.trim().toLowerCase();
  return agents.filter((agent) => {
    if (filter !== "all" && agentFilterOf(agent.status) !== filter) return false;
    if (!needle) return true;
    const haystack = [agent.name, agent.description, agent.type, ...agent.tags, agent.llm_model ? modelLabel(agent.llm_model) : ""].join(" ").toLowerCase();
    return haystack.includes(needle);
  });
}

/** Newest first, so a just-created Agent is at the top before and after a reload. */
export function sortAgents(agents: readonly Agent[]): Agent[] {
  return [...agents].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || a.name.localeCompare(b.name));
}

/** Up to two initials for an Agent's avatar. */
export function agentInitials(name: string): string {
  const words = name.replace(/[^\p{L}\p{N}\s]/gu, " ").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "A";
  return (words.length === 1 ? words[0].slice(0, 2) : `${words[0][0]}${words[1][0]}`).toUpperCase();
}

// ------------------------------------------------------------------ live turn activity

export type LiveStep = { label: string; state: "done" | "active" };

/**
 * The visible progress of an in-flight chat turn, from its real execution record: whether it
 * has started, and which tools its checkpoint says were called. The checkpoint is written
 * before a tool runs, so a tool is shown as "called", never as succeeded; results appear
 * with the saved reply. No invented "thinking" steps.
 */
export function liveTurnSteps(execution: Execution | null): LiveStep[] {
  if (execution === null) return [{ label: "Sending your message", state: "active" }];
  if (execution.status === "pending" || execution.status === "queued") return [{ label: "Waiting to start", state: "active" }];
  const started = execution.checkpoint?.tools_started;
  const tools = Array.isArray(started)
    ? started.map((tool) => (tool && typeof tool === "object" && typeof (tool as { name?: unknown }).name === "string" ? (tool as { name: string }).name : "a tool"))
    : [];
  return [
    { label: "Started", state: "done" },
    ...tools.map((name): LiveStep => ({ label: `Called ${name.replaceAll("_", " ")}`, state: "done" })),
    { label: "Working…", state: "active" },
  ];
}

/** The chat execution currently running for this Agent (and session, when known). */
export function activeChatExecution(executions: readonly Execution[], agentId: string, sessionId: string | null): Execution | null {
  const active = executions.filter((execution) =>
    execution.agent_id === agentId &&
    execution.metadata.kind === "chat" &&
    ["pending", "queued", "starting", "running"].includes(execution.status));
  return active.find((execution) => sessionId === null || execution.metadata.session_id === sessionId) ?? null;
}

// ------------------------------------------------------------------ lifecycle actions

/**
 * Lifecycle actions offered for an Agent. Conversations own RUNNING (manual start, pause
 * or resume could strand an Agent), so only setup and retirement are offered — the same
 * rules the Agents page has always applied.
 */
export type LifecycleAction = "initialize" | "stop" | "delete";

export function lifecycleActionsFor(status: AgentStatus): LifecycleAction[] {
  if (status === "created") return ["initialize", "stop"];
  if (status === "stopped") return ["delete"];
  return status === "initializing" ? [] : ["stop"];
}

/** Settings are editable unless the Agent is mid-turn or retired (unchanged rule). */
export function canEditSettings(status: AgentStatus): boolean {
  return status !== "running" && status !== "stopped";
}
