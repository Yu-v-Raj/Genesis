"use client";

import Link from "next/link";
import { ArrowUpRight, Brain, ShieldCheck } from "lucide-react";

import { ToolRunRow } from "@/components/tools/tool-run";
import { StatusBadge } from "@/components/ui/status-badge";
import { errorCategoryLabel, formatDuration, relativeTime } from "@/lib/operations";
import { toolLabel } from "@/lib/tools";
import { summarizeModelCalls, truncationNote } from "@/lib/traces";
import type { Approval } from "@/types/approvals";
import type { ModelCall, TraceLimits } from "@/types/operations";
import type { ToolTask } from "@/types/tools";

function SectionTitle({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <h3 className="text-xs font-medium text-muted-foreground">
      {children}{count !== undefined && <span className="ml-1.5 tabular-nums text-subtle">{count}</span>}
    </h3>
  );
}

/** Model calls from durable events: provider, model, timing and token use. Never content. */
export function ModelCallsSection({ calls }: { calls: readonly ModelCall[] }) {
  if (calls.length === 0) return null;
  const summary = summarizeModelCalls(calls);
  return (
    <section aria-label="Model calls">
      <SectionTitle count={calls.length}>Model calls</SectionTitle>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {formatDuration(summary.totalSeconds)} in total{summary.totalTokens !== null ? ` · ${summary.totalTokens.toLocaleString()} tokens` : ""}
        {summary.failed > 0 ? ` · ${summary.failed} failed` : ""}
      </p>
      <ol className="mt-1.5 flex flex-col divide-y divide-border rounded-md border border-border bg-surface-2/50">
        {calls.map((call) => (
          <li key={call.sequence} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-xs">
            <Brain aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate text-foreground">{call.model ?? "Unknown model"}<span className="text-muted-foreground">{call.provider ? ` · ${call.provider}` : ""}</span></span>
            {call.attempts != null && call.attempts > 1 && <span className="text-[11px] text-warning">{call.attempts} attempts</span>}
            {call.total_tokens !== null && <span className="text-[11px] tabular-nums text-subtle">{call.total_tokens.toLocaleString()} tokens</span>}
            <span className="text-[11px] tabular-nums text-subtle">{call.duration_ms !== null ? formatDuration(call.duration_ms / 1000) : "—"}</span>
            {call.outcome === "failed" ? <StatusBadge status="failed" label={call.error_category ? `Failed: ${errorCategoryLabel(call.error_category)}` : call.error_type ? `Failed: ${call.error_type}` : "Failed"} /> : <StatusBadge status="completed" label="Answered" />}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Tool runs recorded for this trace, oldest first, with their arguments and results. */
export function ToolRunsSection({ tasks, now, empty }: { tasks: readonly ToolTask[]; now: Date; empty?: string }) {
  return (
    <section aria-label="Tool runs">
      <SectionTitle count={tasks.length}>Tool runs</SectionTitle>
      {tasks.length === 0 ? (
        empty ? <p className="mt-1.5 text-xs text-muted-foreground">{empty}</p> : null
      ) : (
        <ul className="mt-1.5 divide-y divide-border overflow-hidden rounded-md border border-border bg-surface-2/50">
          {tasks.map((task) => <ToolRunRow key={task.task_id} task={task} now={now} showTool links={false} />)}
        </ul>
      )}
    </section>
  );
}

/** Approval requests made for this trace and what became of them. */
export function ApprovalsSection({ approvals, now }: { approvals: readonly Approval[]; now: Date }) {
  if (approvals.length === 0) return null;
  return (
    <section aria-label="Approvals">
      <SectionTitle count={approvals.length}>Approvals</SectionTitle>
      <ul className="mt-1.5 flex flex-col divide-y divide-border rounded-md border border-border bg-surface-2/50">
        {approvals.map((approval) => (
          <li key={approval.approval_id} className="flex flex-col gap-1 px-3 py-2 text-xs">
            <span className="flex flex-wrap items-center gap-2">
              <ShieldCheck aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-foreground">
                {toolLabel(approval.tool_name)}
                {approval.subject.step_name ? <span className="text-muted-foreground"> · step “{approval.subject.step_name}”</span> : null}
              </span>
              <StatusBadge status={approval.state} />
              {approval.outcome && <StatusBadge status={approval.outcome === "unknown" ? "interrupted" : approval.outcome} label={approval.outcome === "unknown" ? "Outcome unknown" : approval.outcome === "completed" ? "Ran" : "Ran and failed"} />}
            </span>
            <span className="flex flex-wrap items-center gap-x-2 pl-5 text-[11px] text-muted-foreground">
              <span>Requested {relativeTime(approval.created_at, now)}</span>
              {approval.decided_at && <><span aria-hidden>·</span><span>decided {relativeTime(approval.decided_at, now)}</span></>}
              {approval.state === "pending" && Date.parse(approval.expires_at) < now.getTime() && <><span aria-hidden>·</span><span className="text-warning">past its deadline</span></>}
              <Link href={`/approvals?approval=${encodeURIComponent(approval.approval_id)}`} className="inline-flex items-center gap-0.5 hover:text-foreground">
                Open<ArrowUpRight aria-hidden className="h-3 w-3" />
              </Link>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function TruncationNote({ limits }: { limits: TraceLimits }) {
  const note = truncationNote(limits);
  return note ? <p className="text-[11px] text-muted-foreground">{note}</p> : null;
}
