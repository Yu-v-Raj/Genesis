/**
 * Pure view logic for the Overview and Operations pages: execution filters, URL state,
 * summary counts and time formatting. Free of React and browser APIs for `node --test`.
 */
import type { Execution, ExecutionStatus } from "@/types/executions";

/** `GET /api/executions` returns at most this many executions, newest first. */
export const EXECUTION_LIST_LIMIT = 200;

const DAY_MS = 24 * 60 * 60 * 1000;

// ------------------------------------------------------------------ status groups

export type StatusFilter = "all" | "active" | "completed" | "attention" | "cancelled";

/** Filter groups over the real execution statuses; every status belongs to exactly one. */
export const STATUS_GROUPS: Readonly<Record<Exclude<StatusFilter, "all">, readonly ExecutionStatus[]>> = {
  active: ["pending", "queued", "starting", "running"],
  completed: ["completed"],
  attention: ["failed", "interrupted", "waiting_approval"],
  cancelled: ["cancelled"],
};

export const STATUS_FILTER_OPTIONS: readonly { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "active", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "attention", label: "Needs attention" },
  { value: "cancelled", label: "Cancelled" },
];

export function inStatusGroup(status: ExecutionStatus, filter: StatusFilter): boolean {
  return filter === "all" || STATUS_GROUPS[filter].includes(status);
}

// ------------------------------------------------------------------ kinds

const KIND_LABELS: Readonly<Record<string, string>> = { chat: "Chat turn", tool: "Tool run", work: "Agent work" };

/** Executions record their kind in metadata; older ones may only name a tool. */
export function executionKind(execution: Execution): string {
  const kind = execution.metadata.kind;
  if (typeof kind === "string" && kind.trim()) return kind;
  return typeof execution.metadata.tool_name === "string" ? "tool" : "work";
}

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind.charAt(0).toUpperCase() + kind.slice(1).replace(/[_-]+/g, " ");
}

// ------------------------------------------------------------------ filters and URL state

export interface ExecutionFilters {
  status: StatusFilter;
  agentId: string | null;
  kind: string | null;
  query: string;
}

export const EMPTY_FILTERS: ExecutionFilters = { status: "all", agentId: null, kind: null, query: "" };

interface ParamReader {
  get(name: string): string | null;
}

const STATUS_FILTERS = new Set<string>(STATUS_FILTER_OPTIONS.map((option) => option.value));

/** Read filters from the URL; unknown values fall back to "no filter" instead of hiding data. */
export function filtersFromParams(params: ParamReader): ExecutionFilters {
  const status = params.get("status");
  return {
    status: status && STATUS_FILTERS.has(status) ? (status as StatusFilter) : "all",
    agentId: params.get("agent") || null,
    kind: params.get("kind") || null,
    query: params.get("q") ?? "",
  };
}

export function hasActiveFilters(filters: ExecutionFilters): boolean {
  return filters.status !== "all" || filters.agentId !== null || filters.kind !== null || filters.query.trim() !== "";
}

/** The Operations URL query for a view; empty values are left out. */
export function operationsQuery(view: Partial<ExecutionFilters> & { execution?: string | null; run?: string | null; tab?: string | null }): string {
  const params = new URLSearchParams();
  if (view.tab && view.tab !== "executions") params.set("tab", view.tab);
  if (view.status && view.status !== "all") params.set("status", view.status);
  if (view.agentId) params.set("agent", view.agentId);
  if (view.kind) params.set("kind", view.kind);
  if (view.query?.trim()) params.set("q", view.query.trim());
  if (view.execution) params.set("execution", view.execution);
  if (view.run) params.set("run", view.run);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function filterExecutions(executions: readonly Execution[], filters: ExecutionFilters, agentNames: Readonly<Record<string, string>> = {}): Execution[] {
  const query = filters.query.trim().toLowerCase();
  return executions.filter((execution) => {
    if (!inStatusGroup(execution.status, filters.status)) return false;
    if (filters.agentId && execution.agent_id !== filters.agentId) return false;
    if (filters.kind && executionKind(execution) !== filters.kind) return false;
    if (!query) return true;
    const message = typeof execution.metadata.message === "string" ? execution.metadata.message : "";
    const tool = typeof execution.metadata.tool_name === "string" ? execution.metadata.tool_name : "";
    const haystack = [execution.execution_id, agentNames[execution.agent_id] ?? "", message, tool, execution.error_category ?? ""].join(" ").toLowerCase();
    return haystack.includes(query);
  });
}

// ------------------------------------------------------------------ summaries

export interface ExecutionSummary {
  /** Executions created in the last 24 hours. */
  last24h: number;
  completed24h: number;
  /** Failed or interrupted in the last 24 hours. */
  attention24h: number;
  /** In progress right now. */
  active: number;
  /**
   * The API returns only the newest executions; when all of them fall inside the window,
   * older ones in the window may be missing, so counts are lower bounds ("200+").
   */
  capped: boolean;
}

export function summarizeExecutions(executions: readonly Execution[], now: Date): ExecutionSummary {
  const since = now.getTime() - DAY_MS;
  const recent = executions.filter((execution) => Date.parse(execution.created_at) >= since);
  const oldest = executions[executions.length - 1];
  return {
    last24h: recent.length,
    completed24h: recent.filter((execution) => execution.status === "completed").length,
    attention24h: recent.filter((execution) => inStatusGroup(execution.status, "attention")).length,
    active: executions.filter((execution) => inStatusGroup(execution.status, "active")).length,
    capped: executions.length >= EXECUTION_LIST_LIMIT && oldest !== undefined && Date.parse(oldest.created_at) >= since,
  };
}

export function countLabel(count: number, capped: boolean): string {
  return capped ? `${count}+` : String(count);
}

export interface AgentStatusSummary {
  total: number;
  ready: number;
  working: number;
  /** Paused, failed, stopped, or not yet initialized. */
  other: number;
}

export function summarizeAgents(statuses: readonly string[]): AgentStatusSummary {
  const ready = statuses.filter((status) => status === "idle").length;
  const working = statuses.filter((status) => status === "running" || status === "initializing" || status === "waiting").length;
  return { total: statuses.length, ready, working, other: statuses.length - ready - working };
}

// ------------------------------------------------------------------ time

export function relativeTime(iso: string | null | undefined, now: Date): string {
  if (!iso) return "—";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "—";
  const seconds = Math.round((now.getTime() - then) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min ${Math.round(seconds % 60)} s`;
}

export function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)} s`;
  if (seconds < 3_600) return `${Math.floor(seconds / 60)} min`;
  return `${Math.floor(seconds / 3_600)} h ${Math.floor((seconds % 3_600) / 60)} min`;
}

// ------------------------------------------------------------------ errors

const ERROR_CATEGORIES: Readonly<Record<string, string>> = {
  configuration: "Configuration problem",
  timeout: "Timed out",
  provider_error: "Model provider error",
  rate_limited: "Rate limited by the model provider",
  provider_unavailable: "Model provider temporarily unavailable",
  invalid_response: "Unreadable model response",
  cancelled: "Cancelled",
  agent_unavailable: "Agent unavailable",
  invalid_request: "Invalid request",
  conflict: "Conflicting update",
  storage: "Storage error",
  chat_failed: "Chat failed",
  tool_failed: "Tool failed",
  tool_denied: "Refused by tool policy",
  execution_failed: "Run failed",
  interrupted: "Interrupted by a restart",
};

/**
 * What a category means, where the label alone could mislead. A refusal and a failure are
 * different: a refused tool never started; a failed one ran and reported an error.
 */
const ERROR_EXPLANATIONS: Readonly<Record<string, string>> = {
  tool_denied:
    "The server's tool policy refused this call before the tool ran, so nothing was executed. For example, the tool isn't in the Agent's allowed tools, it's disabled, or its arguments were invalid or too large.",
  tool_failed: "The tool started running and then reported a failure.",
  rate_limited: "The provider kept refusing requests for being over its rate limit or quota, so Genesis gave up after its retries. Try again later.",
  provider_unavailable: "The provider was overloaded or unreachable on every attempt. Retries only repeat the model request; no tool ran twice.",
};

export function errorCategoryExplanation(category: string | null | undefined): string | null {
  return category ? ERROR_EXPLANATIONS[category] ?? null : null;
}

/** A readable name for a backend error category; unknown categories are shown as written. */
export function errorCategoryLabel(category: string | null | undefined): string | null {
  if (!category) return null;
  return ERROR_CATEGORIES[category] ?? category.replace(/[_-]+/g, " ");
}
