/**
 * Pure view logic for durable executions and workflow runs. The server decides what is
 * retryable; these helpers only turn its answers into words. Free of React and browser
 * APIs so it can be tested with `node --test`.
 */
import type { Execution, ExecutionStatus, ExecutionTransition, RetryInfo } from "@/types/executions";
import type { WorkflowStatus, WorkflowTaskStatus } from "@/types/workflows";
import { statusPresentation } from "./status.ts";

type AnyStatus = ExecutionStatus | WorkflowStatus | WorkflowTaskStatus;

/** Fuller wording for durable work, where the short badge label needs context. */
const DESCRIPTIONS: Partial<Record<AnyStatus, string>> = {
  interrupted: "Interrupted — needs a decision",
  created: "Not started",
  blocked: "Blocked by a failed step",
};

/** Labels come from lib/status.ts, the single status vocabulary. */
export function statusText(status: AnyStatus): string {
  return DESCRIPTIONS[status] ?? statusPresentation(status).label;
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

export function isChat(execution: Execution): boolean {
  return execution.metadata.kind === "chat";
}

/** A short, human description of what an execution was doing. */
export function executionLabel(execution: Execution, agentName?: string): string {
  if (isChat(execution)) {
    const message = typeof execution.metadata.message === "string" ? execution.metadata.message : "";
    const preview = message.length > 60 ? `${message.slice(0, 57)}…` : message;
    return `${agentName ? `Chat with ${agentName}` : "Chat"}: “${preview}”`;
  }
  if (typeof execution.metadata.tool_name === "string") return `Tool: ${execution.metadata.tool_name}`;
  return "Agent work";
}

/** Tools a chat started before it ended, from its checkpoint (names only). */
export function startedTools(execution: Execution): string[] {
  const started = execution.checkpoint?.tools_started;
  if (!Array.isArray(started)) return [];
  return started.map((tool) => (tool && typeof tool === "object" && typeof (tool as { name?: unknown }).name === "string" ? (tool as { name: string }).name : "tool"));
}

/**
 * Chat messages in this session whose turn never finished (failed, cancelled, or
 * interrupted) and that have not already been retried. Their message is not in the
 * conversation, so the UI offers them separately.
 */
export function unfinishedChats(executions: Execution[], sessionId: string | null): Execution[] {
  if (sessionId === null) return [];
  const retried = new Set(executions.map((execution) => execution.retry_of).filter((id): id is string => id !== null));
  return executions.filter(
    (execution) =>
      isChat(execution) &&
      execution.metadata.session_id === sessionId &&
      ["failed", "cancelled", "interrupted"].includes(execution.status) &&
      !retried.has(execution.execution_id),
  );
}
