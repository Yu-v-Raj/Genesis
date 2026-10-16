"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Check, Play, ShieldAlert, Undo2, X } from "lucide-react";

import { Button, IconButton } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { JsonView } from "@/components/ui/disclosure";
import { Alert } from "@/components/ui/feedback";
import { StatusBadge } from "@/components/ui/status-badge";
import type { ActionResult, ApprovalAction } from "@/hooks/use-approvals";
import {
  approveEffect,
  decisionSourceText,
  expiryText,
  rejectEffect,
  relatedLinks,
  requesterText,
  stateSummary,
} from "@/lib/approvals";
import { relativeTime } from "@/lib/operations";
import { toolLabel } from "@/lib/tools";
import type { Approval } from "@/types/approvals";

/**
 * One approval request, explained: what would run, who asked, with which (redacted)
 * arguments, why approval is needed and what deciding does. Controls follow the server's
 * `can_*` flags; a decision is shown only after the server confirms it.
 */
export function ApprovalDetail({ approval, now, busy, onAct, onBack }: { approval: Approval; now: Date; busy: boolean; onAct: (action: ApprovalAction) => Promise<ActionResult>; onBack: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "danger" | "success" | "warning"; text: string; output?: unknown } | null>(null);
  const links = relatedLinks(approval);

  async function run(action: ApprovalAction) {
    setFeedback(null);
    const outcome = await onAct(action);
    setConfirming(false);
    if (outcome.result === null) return setFeedback({ tone: "danger", text: outcome.error });
    const { result } = outcome;
    if (result.problem) return setFeedback({ tone: "warning", text: `Approved, but it did not run: ${result.problem}` });
    if (result.task) return setFeedback({ tone: "success", text: "The test ran once.", output: result.task.result?.output ?? null });
    setFeedback({ tone: "success", text: action === "approve" ? "Approval recorded." : action === "reject" ? "Rejection recorded." : "Request updated." });
  }

  return (
    <article aria-labelledby={`approval-${approval.approval_id}`} className="flex flex-col gap-5">
      <header className="flex items-start gap-3">
        <IconButton label="Back to the list" onClick={onBack} className="-ml-1 lg:hidden"><ArrowLeft aria-hidden className="h-4 w-4" /></IconButton>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id={`approval-${approval.approval_id}`} className="text-base font-semibold text-foreground">Run {toolLabel(approval.tool_name)}?</h2>
            <StatusBadge status={approval.state} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{stateSummary(approval)}</p>
        </div>
      </header>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-[9rem_minmax(0,1fr)]">
        <dt className="text-muted-foreground">Requested by</dt>
        <dd className="text-foreground">{requesterText(approval)}</dd>
        <dt className="text-muted-foreground">Tool</dt>
        <dd className="min-w-0">
          <span className="font-mono text-foreground">{approval.tool_name}</span>
          <span className="text-subtle"> · v{approval.tool_version}</span>
          <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{approval.tool_description ?? "This tool is no longer registered, so its description isn't available."}</p>
        </dd>
        <dt className="text-muted-foreground">Why approval</dt>
        <dd className="text-foreground">{approval.reason}</dd>
        <dt className="text-muted-foreground">Requested</dt>
        <dd className="text-foreground"><time dateTime={approval.created_at} title={new Date(approval.created_at).toLocaleString()}>{relativeTime(approval.created_at, now)}</time></dd>
        {(approval.state === "pending" || approval.state === "approved") && (
          <>
            <dt className="text-muted-foreground">Deadline</dt>
            <dd className="text-foreground"><time dateTime={approval.expires_at} title={new Date(approval.expires_at).toLocaleString()}>{expiryText(approval.expires_at, now)}</time></dd>
          </>
        )}
        {approval.decided_at && (
          <>
            <dt className="text-muted-foreground">Decided</dt>
            <dd className="text-foreground">
              <time dateTime={approval.decided_at} title={new Date(approval.decided_at).toLocaleString()}>{relativeTime(approval.decided_at, now)}</time>
              {approval.decision_source && <span className="text-muted-foreground"> · through {decisionSourceText(approval.decision_source)}</span>}
            </dd>
          </>
        )}
      </dl>

      <section aria-labelledby={`arguments-${approval.approval_id}`} className="flex flex-col gap-2">
        <h3 id={`arguments-${approval.approval_id}`} className="text-xs font-medium uppercase tracking-wider text-subtle">Exact arguments</h3>
        {Object.keys(approval.arguments).length === 0 ? <p className="text-sm text-muted-foreground">No arguments.</p> : <JsonView value={approval.arguments} />}
        {approval.redacted_fields.length > 0 && (
          <Alert tone="info">
            Hidden here because they look secret: <span className="font-mono">{approval.redacted_fields.join(", ")}</span>. The exact values are stored with the request and are what would be used.
          </Alert>
        )}
      </section>

      {approval.detail && approval.state !== "expired" && approval.state !== "cancelled" && <p className="text-sm text-muted-foreground">{approval.detail}</p>}

      {approval.can_decide && (
        <section aria-label="Decision" className="flex flex-col gap-3 rounded-lg border border-border bg-surface-2/50 p-4">
          <div className="grid gap-3 text-xs leading-5 sm:grid-cols-2">
            <p><span className="font-medium text-foreground">Approve:</span> <span className="text-muted-foreground">{approveEffect(approval)}</span></p>
            <p><span className="font-medium text-foreground">Reject:</span> <span className="text-muted-foreground">{rejectEffect(approval)}</span></p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" size="sm" icon={<Check aria-hidden className="h-3.5 w-3.5" />} onClick={() => setConfirming(true)} disabled={busy}>Approve…</Button>
            <Button size="sm" icon={<X aria-hidden className="h-3.5 w-3.5" />} onClick={() => void run("reject")} loading={busy && !confirming} disabled={busy}>Reject</Button>
          </div>
        </section>
      )}
      {!approval.can_decide && (approval.can_run || approval.can_cancel) && (
        <div className="flex flex-wrap gap-2">
          {approval.can_run && <Button variant="primary" size="sm" icon={<Play aria-hidden className="h-3.5 w-3.5" />} onClick={() => void run("run")} loading={busy} disabled={busy}>Run the approved test</Button>}
          {approval.can_cancel && <Button size="sm" icon={<Undo2 aria-hidden className="h-3.5 w-3.5" />} onClick={() => void run("cancel")} disabled={busy}>Withdraw approval</Button>}
        </div>
      )}

      <div aria-live="polite">
        {feedback && (
          <Alert tone={feedback.tone}>
            <p>{feedback.text}</p>
            {feedback.output !== undefined && feedback.output !== null && <JsonView value={feedback.output} className="mt-2" />}
          </Alert>
        )}
      </div>

      {links.length > 0 && (
        <nav aria-label="Related" className="flex flex-wrap gap-x-4 gap-y-1">
          {links.map((link) => (
            <Link key={link.href} href={link.href} className="inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground">
              {link.label}<ArrowUpRight aria-hidden className="h-3 w-3" />
            </Link>
          ))}
        </nav>
      )}

      <Dialog
        open={confirming}
        onClose={() => { if (!busy) setConfirming(false); }}
        title={`Approve ${toolLabel(approval.tool_name)}?`}
        description={approveEffect(approval)}
        footer={
          <>
            {/* Focus starts on the safe choice, so a stray Enter never approves. */}
            <Button size="sm" onClick={() => setConfirming(false)} disabled={busy} data-autofocus>Keep reviewing</Button>
            <Button variant="primary" size="sm" onClick={() => void run("approve")} loading={busy}>Approve this call</Button>
          </>
        }
      >
        <div className="flex gap-2 text-sm text-muted-foreground">
          <ShieldAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="flex flex-col gap-1">
            <p>{approval.tool_description ?? approval.reason}</p>
            <p>Requested by: {requesterText(approval)}. Approving authorizes only these arguments, once.</p>
          </div>
        </div>
      </Dialog>
    </article>
  );
}
