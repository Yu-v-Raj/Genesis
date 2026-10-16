/**
 * Pure view logic for execution and workflow traces and the durable event history.
 * Free of React and browser APIs for `node --test`.
 */
import type { ModelCall, RuntimeEvent, RuntimeEventQuery, TraceLimits, WorkflowTransition } from "@/types/operations";
import type { RealtimeEvent } from "@/types/realtime";

// ------------------------------------------------------------------ workflow timeline

const RUN_CHANGES: Readonly<Record<string, string>> = {
  created: "Run created",
  queued: "Run queued",
  paused: "Run paused",
  waiting_approval: "Run waiting for an approval decision",
  completed: "Run completed",
  failed: "Run failed",
  cancelled: "Run cancelled",
  interrupted: "Run interrupted: Genesis stopped while a step was running",
};

const STEP_CHANGES: Readonly<Record<string, string>> = {
  ready: "is ready to run",
  running: "started",
  completed: "completed",
  failed: "failed",
  waiting_approval: "is waiting for approval",
  blocked: "was blocked by a failed dependency",
  cancelled: "was cancelled",
  interrupted: "was interrupted; its outcome is unknown",
};

/** One readable line per recorded change of a run or one of its steps. */
export function describeWorkflowTransition(change: WorkflowTransition, stepNames: Readonly<Record<string, string>> = {}): string {
  if (change.step_id === null) {
    if (change.to_status === "running") return change.worker ? `Run claimed by worker ${change.worker}` : "Run started";
    if (change.to_status === "queued" && change.from_status === "waiting_approval") return "Run queued again after an approval decision";
    if (change.to_status === "queued" && change.from_status !== null && change.from_status !== "created") {
      return change.from_status === "failed" || change.from_status === "interrupted" ? `Run queued for attempt ${change.attempt}` : "Run queued again";
    }
    return RUN_CHANGES[change.to_status] ?? `Run ${change.to_status.replace(/_/g, " ")}`;
  }
  const name = stepNames[change.step_id] ?? change.step_id;
  let verb = STEP_CHANGES[change.to_status];
  if (change.to_status === "pending") {
    verb = change.from_status === "waiting_approval"
      ? "was approved and will run"
      : change.from_status === "running" || change.from_status === "ready"
        ? "will run again (its run was recovered)"
        : "was reset to run again";
  }
  return `Step “${name}” ${verb ?? change.to_status.replace(/_/g, " ")}`;
}

/** Distinct attempts in a timeline, oldest first (a retry starts a new attempt). */
export function attemptsOf(changes: readonly WorkflowTransition[]): number[] {
  return [...new Set(changes.map((change) => change.attempt))].sort((a, b) => a - b);
}

// ------------------------------------------------------------------ model calls

export interface ModelCallSummary {
  count: number;
  failed: number;
  /** `null` when no call reported token usage. */
  totalTokens: number | null;
  totalSeconds: number;
}

export function summarizeModelCalls(calls: readonly ModelCall[]): ModelCallSummary {
  const tokens = calls.map((call) => call.total_tokens).filter((value): value is number => typeof value === "number");
  return {
    count: calls.length,
    failed: calls.filter((call) => call.outcome === "failed").length,
    totalTokens: tokens.length ? tokens.reduce((sum, value) => sum + value, 0) : null,
    totalSeconds: calls.reduce((sum, call) => sum + (call.duration_ms ?? 0), 0) / 1000,
  };
}

// ------------------------------------------------------------------ limits

/** What a cut list means, or `null` when nothing was cut. */
export function truncationNote(limits: TraceLimits): string | null {
  const cut = [limits.tool_tasks && "tool runs", limits.approvals && "approvals", limits.events && "events"].filter(Boolean) as string[];
  if (!cut.length) return null;
  const list = cut.length === 1 ? cut[0] : `${cut.slice(0, -1).join(", ")} and ${cut[cut.length - 1]}`;
  return `This trace is long, so only the most recent ${list} are shown.`;
}

// ------------------------------------------------------------------ durable events

export const DURABLE_EVENT_FILTERS: readonly { value: string; label: string; eventType: string | null }[] = [
  { value: "all", label: "All", eventType: null },
  { value: "execution", label: "Runs", eventType: "execution." },
  { value: "model", label: "Model calls", eventType: "llm." },
  { value: "tool", label: "Tool runs", eventType: "task." },
  { value: "refusal", label: "Refusals", eventType: "tool.rejected" },
  { value: "approval", label: "Approvals", eventType: "approval." },
  { value: "workflow", label: "Workflows", eventType: "workflow." },
];

/** The query string for a page of stored events; empty values are left out. */
export function eventsSearch(query: RuntimeEventQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const search = params.toString();
  return search ? `?${search}` : "";
}

export function eventFilterType(value: string): string | null {
  return DURABLE_EVENT_FILTERS.find((filter) => filter.value === value)?.eventType ?? null;
}

/** Whether a live event is one the durable history also keeps (so a refresh is worth it). */
export function isDurableEventType(eventType: string): boolean {
  return ["execution.", "workflow.", "task.", "approval."].some((prefix) => eventType.startsWith(prefix))
    || eventType === "tool.rejected" || eventType === "llm.completed" || eventType === "llm.failed" || eventType === "llm.retrying";
}

/** Merge pages of stored events: no duplicates, newest first. */
export function mergeEvents(current: readonly RuntimeEvent[], incoming: readonly RuntimeEvent[]): RuntimeEvent[] {
  const bySequence = new Map<number, RuntimeEvent>();
  for (const event of [...current, ...incoming]) bySequence.set(event.sequence, event);
  return [...bySequence.values()].sort((a, b) => b.sequence - a.sequence);
}

/** The shape the event descriptions understand. */
export function asRealtimeEvent(event: RuntimeEvent): RealtimeEvent {
  return { id: event.event_id, timestamp: event.occurred_at, event_type: event.event_type, source: event.source, payload: event.payload as RealtimeEvent["payload"] };
}

/** Merge pages of tool runs or other records keyed by id: no duplicates, newest first. */
export function mergeById<T>(current: readonly T[], incoming: readonly T[], id: (item: T) => string, at: (item: T) => string | null | undefined): T[] {
  const byId = new Map<string, T>();
  for (const item of [...current, ...incoming]) byId.set(id(item), item);
  return [...byId.values()].sort((a, b) => Date.parse(at(b) ?? "") - Date.parse(at(a) ?? "") || 0);
}
