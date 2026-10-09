/**
 * Pure view logic for durable executions and workflow runs. The server decides what is
 * retryable; these helpers only turn its answers into words. Free of React and browser
 * APIs so it can be tested with `node --test`.
 */
import type { ExecutionStatus, ExecutionTransition, RetryInfo } from "@/types/executions";
import type { WorkflowStatus, WorkflowTaskStatus } from "@/types/workflows";

type AnyStatus = ExecutionStatus | WorkflowStatus | WorkflowTaskStatus;

const STATUS_TEXT: Record<AnyStatus, string> = {
  pending: "Pending",
  queued: "Queued",
  starting: "Starting",
  running: "Running",
  completed: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
  interrupted: "Interrupted — needs a decision",
  created: "Not started",
  paused: "Paused",
  ready: "Ready",
  blocked: "Blocked by a failed step",
};

export function statusText(status: AnyStatus): string {
  return STATUS_TEXT[status] ?? status;
}

export function isActive(status: AnyStatus): boolean {
  return ["pending", "queued", "starting", "running", "ready", "paused"].includes(status);
}

export interface RetryPresentation {
  /** Show a retry control at all. */
  visible: boolean;
  /** The user must tick a confirmation before the request is sent. */
  needsConfirmation: boolean;
  label: string;
  explanation: string;
}

/** Turn the server's retry decision into a control description; never invents permission. */
export function retryPresentation(retry: RetryInfo | null): RetryPresentation {
  if (retry === null || !retry.allowed) {
    return { visible: false, needsConfirmation: false, label: "", explanation: retry?.reason ?? "" };
  }
  return {
    visible: true,
    needsConfirmation: retry.requires_acknowledgement,
    label: retry.requires_acknowledgement ? "Retry anyway" : "Retry",
    explanation: retry.reason,
  };
}

/** One readable line per recorded state change, oldest first. */
export function describeTransition(transition: ExecutionTransition): string {
  const to = statusText(transition.to_status);
  if (transition.detail && transition.detail !== transition.to_status) return `${to} — ${transition.detail}`;
  return to;
}
