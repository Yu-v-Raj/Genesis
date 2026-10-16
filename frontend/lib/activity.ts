/**
 * Readable descriptions of runtime events for the Operations event stream.
 *
 * Only wording is derived here; the raw event stays available in the UI's technical
 * details. Unknown event types fall back to their name, so nothing is hidden.
 */
import type { RealtimeEvent } from "@/types/realtime";
import { kindLabel } from "./operations.ts";
import { statusPresentation } from "./status.ts";

export type EventCategory = "agent" | "execution" | "model" | "tool" | "approval" | "memory" | "workflow" | "system" | "log";

export const EVENT_CATEGORIES: readonly { value: EventCategory | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "agent", label: "Agents" },
  { value: "execution", label: "Runs" },
  { value: "model", label: "Models" },
  { value: "tool", label: "Tools" },
  { value: "approval", label: "Approvals" },
  { value: "memory", label: "Memory" },
  { value: "workflow", label: "Workflows" },
  { value: "system", label: "System" },
];

export function eventCategory(eventType: string): EventCategory {
  const prefix = eventType.split(".")[0];
  if (prefix === "agent") return "agent";
  if (prefix === "execution") return "execution";
  if (prefix === "llm") return "model";
  if (prefix === "tool" || prefix === "task") return "tool";
  if (prefix === "approval") return "approval";
  if (prefix === "memory" || prefix === "memory_provider") return "memory";
  if (prefix === "workflow") return "workflow";
  if (prefix === "log") return "log";
  return "system";
}

/** Heartbeats and log lines have their own views; they would drown the event stream. */
export function isRoutineEvent(eventType: string): boolean {
  return eventType === "system.heartbeat" || eventType === "log.created";
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : typeof value === "number" ? String(value) : null;
}

function humanize(eventType: string): string {
  const words = eventType.replace(/[._]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const AGENT_ACTIONS: Readonly<Record<string, string>> = {
  created: "Agent created",
  registered: "Agent registered",
  initialized: "Agent initialized",
  restored: "Agent restored after restart",
  started: "Agent started work",
  paused: "Agent paused",
  resumed: "Agent resumed",
  completed: "Agent finished work",
  failed: "Agent failed",
  stopped: "Agent stopped",
  deleted: "Agent deleted",
  removed: "Agent removed",
  session_created: "New conversation started",
  configuration_updated: "Agent settings updated",
  metadata_updated: "Agent details updated",
  context_updated: "Agent context updated",
};

const EXECUTION_ACTIONS: Readonly<Record<string, string>> = {
  created: "created",
  queued: "queued",
  started: "started",
  progress: "in progress",
  completed: "completed",
  failed: "failed",
  cancelled: "cancelled",
  interrupted: "interrupted",
  recovered: "recovered after restart",
};

const WORKFLOW_RUN_ACTIONS: Readonly<Record<string, string>> = {
  created: "created",
  queued: "queued",
  started: "started",
  paused: "paused",
  resumed: "resumed",
  completed: "completed",
  failed: "failed",
  cancelled: "cancelled",
  interrupted: "interrupted",
  recovered: "recovered after restart",
  retried: "queued for another attempt",
  waiting_approval: "waiting for an approval decision",
};

const WORKFLOW_STEP_ACTIONS: Readonly<Record<string, string>> = {
  ready: "is ready",
  started: "started",
  completed: "completed",
  failed: "failed",
  interrupted: "was interrupted",
  waiting_approval: "is waiting for approval",
};

const APPROVAL_ACTIONS: Readonly<Record<string, string>> = {
  requested: "Approval requested",
  approved: "Approved",
  rejected: "Rejected",
  expired: "Approval expired",
  cancelled: "Approval request cancelled",
  consumed: "Approved call started",
  outcome: "Approved call finished",
};

/** A one-line description, using an Agent name when the payload identifies one. */
export function describeEvent(event: RealtimeEvent, agentNames: Readonly<Record<string, string>> = {}): string {
  const [prefix, ...rest] = event.event_type.split(".");
  const action = rest.join(".");
  const payload = event.payload;
  const agent = text(payload.agent_id) ? agentNames[String(payload.agent_id)] : undefined;
  const forAgent = agent ? ` · ${agent}` : "";

  if (prefix === "agent") {
    if (action === "status_changed" && text(payload.status)) {
      return `${agent ?? "Agent"} is now ${statusPresentation(String(payload.status)).label.toLowerCase()}`;
    }
    const name = action === "registered" ? text(payload.name) : null;
    return `${AGENT_ACTIONS[action] ?? humanize(event.event_type)}${name ? `: ${name}` : forAgent}`;
  }
  if (prefix === "execution") {
    const kind = text(payload.kind);
    const subject = kind ? kindLabel(kind) : "Run";
    const step = action === "progress" ? text(payload.step) : null;
    return `${subject} ${EXECUTION_ACTIONS[action] ?? action.replace(/_/g, " ")}${step ? ` (${step})` : ""}${forAgent}`;
  }
  if (prefix === "llm") {
    const model = text(payload.model) ?? text(payload.provider) ?? "model";
    if (action === "requested") return `Model request sent to ${model}${forAgent}`;
    if (action === "completed") {
      const ms = Number(payload.duration_ms);
      return `${model} responded${Number.isFinite(ms) ? ` in ${(ms / 1000).toFixed(1)} s` : ""}${forAgent}`;
    }
    if (action === "failed") return `${model} request failed${forAgent}`;
    if (action === "retrying") {
      const attempt = Number(payload.attempt);
      return `${model} request failed temporarily${Number.isFinite(attempt) ? ` (attempt ${attempt})` : ""}; retrying${forAgent}`;
    }
  }
  if (prefix === "tool" || prefix === "task") {
    const tool = text(payload.tool_name) ?? text(payload.name) ?? "Tool";
    if (action === "registered") return `Tool registered: ${tool}`;
    if (event.event_type === "tool.rejected") {
      // A refusal is not a failure: the tool never started.
      if (payload.reason === "approval_required") return `${tool} held for the operator's approval`;
      const reason = text(payload.reason);
      return `${tool} refused by tool policy${reason ? ` (${reason.replace(/_/g, " ")})` : ""}`;
    }
    return `${tool} ${action.replace(/_/g, " ") || "event"}`;
  }
  if (prefix === "workflow") {
    const step = text(payload.task_id);
    if (action.startsWith("task.") && step) return `Workflow step “${step}” ${WORKFLOW_STEP_ACTIONS[action.slice(5)] ?? action.slice(5).replace(/_/g, " ")}`;
    if (action.startsWith("definition.")) return action === "definition.created" ? "Workflow saved" : "Workflow updated";
    return `Workflow run ${WORKFLOW_RUN_ACTIONS[action] ?? action.replace(/[._]/g, " ")}`;
  }
  if (prefix === "approval") {
    const tool = text(payload.tool_name) ?? "a tool call";
    return `${APPROVAL_ACTIONS[action] ?? `Approval ${action.replace(/_/g, " ")}`} · ${tool}`;
  }
  if (event.event_type === "service.registered") return `Service registered: ${text(payload.service) ?? "unknown"}`;
  if (event.event_type === "service.removed") return `Service removed: ${text(payload.service) ?? "unknown"}`;
  if (event.event_type === "system.started") return "Genesis started";
  if (event.event_type === "system.stopped") return "Genesis stopped";
  if (event.event_type === "system.heartbeat") return "Heartbeat";
  if (event.event_type === "log.created") return text(payload.message) ?? "Log entry";
  return humanize(event.event_type);
}
