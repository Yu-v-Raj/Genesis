/**
 * Pure view logic for approval requests: who is asking, what deciding will do, and where
 * the related work lives. Every statement is derived from the server's record; nothing
 * here decides what is allowed (the server's `can_*` flags do).
 */
import type { Approval, ApprovalState } from "@/types/approvals";

export const DECIDED_STATES: readonly ApprovalState[] = ["approved", "rejected", "expired", "consumed", "cancelled"];

export function isPending(approval: Approval): boolean {
  return approval.state === "pending";
}

/** Pending requests first (oldest first, so nothing waits behind newer ones), then history newest first. */
export function splitApprovals(approvals: readonly Approval[]): { pending: Approval[]; history: Approval[] } {
  const pending = approvals.filter(isPending).sort((a, b) => a.created_at.localeCompare(b.created_at));
  const history = approvals.filter((item) => !isPending(item)).sort((a, b) => (b.decided_at ?? b.created_at).localeCompare(a.decided_at ?? a.created_at));
  return { pending, history };
}

/** Who asked, from the request's real execution context. */
export function requesterText(approval: Approval): string {
  const { subject } = approval;
  if (approval.caller === "agent") return `Agent ${subject.agent_name ?? "(no longer exists)"}, during a conversation`;
  if (approval.caller === "workflow") {
    const step = subject.step_name ?? subject.step_id ?? "a step";
    const attempt = subject.attempt && subject.attempt > 1 ? ` (attempt ${subject.attempt})` : "";
    return `Workflow ${subject.workflow_name ?? "(no longer exists)"}, step “${step}”${attempt}`;
  }
  if (approval.caller === "operator") return "A test run from the Tools page";
  return approval.caller;
}

/** What approving will do, by caller. Approval authorizes this exact call once. */
export function approveEffect(approval: Approval): string {
  if (approval.caller === "agent") return "The conversation continues and runs this call once, with exactly these arguments. If the Agent's settings changed meanwhile, it won't run.";
  if (approval.caller === "workflow") return "The step runs this call once, with exactly these arguments; then the steps that depend on it can continue.";
  return "The test runs now, once, with exactly these arguments.";
}

export function rejectEffect(approval: Approval): string {
  if (approval.caller === "agent") return "The call doesn't run. The Agent is told it was rejected and the conversation continues.";
  if (approval.caller === "workflow") return "The step doesn't run and fails; steps that depend on it are blocked.";
  return "The test doesn't run.";
}

/** Plain-language state of a request, including what happened after approval. */
export function stateSummary(approval: Approval): string {
  switch (approval.state) {
    case "pending": return "Waiting for your decision. Nothing has run.";
    case "approved": return approval.caller === "operator"
      ? "Approved, but the test hasn't run yet."
      : "Approved. The waiting work will use it shortly.";
    case "rejected": return "Rejected. The call did not run.";
    case "expired": return approval.detail ?? "Expired. The call did not run.";
    case "cancelled": return approval.detail ?? "Cancelled. The call did not run.";
    case "consumed":
      if (approval.outcome === "completed") return "Approved and used: the call ran and completed.";
      if (approval.outcome === "failed") return "Approved and used: the call ran but the tool reported a failure.";
      if (approval.outcome === "unknown") return "Approved and used, but Genesis stopped while it ran, so its outcome is unknown. It was not re-run.";
      return "Approved and used: the call has started.";
  }
}

/** "in 12 min" / "2 min ago" for the request's deadline. */
export function expiryText(expiresAt: string, now: Date): string {
  const ms = new Date(expiresAt).getTime() - now.getTime();
  const minutes = Math.round(Math.abs(ms) / 60_000);
  const span = minutes < 1 ? "less than a minute" : minutes < 90 ? `${minutes} min` : `${Math.round(minutes / 60)} h`;
  return ms > 0 ? `Expires in ${span}` : `Expired ${span} ago`;
}

export function decisionSourceText(source: string | null): string | null {
  if (source === "local_operator_console") return "the Genesis console on this machine";
  if (source === "local_api_client") return "a local API client (no browser origin)";
  if (source === "system") return "Genesis (automatically)";
  return source;
}

/** Where the related work is visible, when the record supports a link. */
export function relatedLinks(approval: Approval): { label: string; href: string }[] {
  const { subject } = approval;
  const links: { label: string; href: string }[] = [];
  if (subject.agent_id) links.push({ label: "Open the Agent", href: `/agents?agent=${encodeURIComponent(subject.agent_id)}` });
  if (subject.execution_id) links.push({ label: "Open the execution in Operations", href: `/monitoring?execution=${encodeURIComponent(subject.execution_id)}` });
  if (subject.workflow_id) links.push({ label: "Open the workflow run", href: `/workflows?tab=runs&run=${encodeURIComponent(subject.workflow_id)}` });
  if (approval.task_id || approval.caller === "operator") links.push({ label: "Open the tool", href: `/tools?tool=${encodeURIComponent(approval.tool_name)}` });
  return links;
}

/** The approval a paused chat execution waits on, from its (server-filtered) checkpoint. */
export function awaitedApproval(checkpoint: Record<string, unknown> | null | undefined): string | null {
  const awaiting = checkpoint?.awaiting;
  if (!awaiting || typeof awaiting !== "object") return null;
  const token = (awaiting as { token?: unknown }).token;
  return typeof token === "string" ? token : null;
}
