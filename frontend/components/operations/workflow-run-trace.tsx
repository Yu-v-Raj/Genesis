"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight } from "lucide-react";

import { ApprovalsSection, ToolRunsSection, TruncationNote } from "@/components/operations/trace-sections";
import { StepList } from "@/components/workflows/step-list";
import { IconButton } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { Alert, Skeleton } from "@/components/ui/feedback";
import { StatusBadge, StatusDot } from "@/components/ui/status-badge";
import { formatDuration } from "@/lib/operations";
import { statusPresentation } from "@/lib/status";
import { attemptsOf, describeWorkflowTransition } from "@/lib/traces";
import { runProgress } from "@/lib/workflows";
import { OperationsApiError, OperationsService } from "@/services/operations.service";
import type { WorkflowTrace } from "@/types/operations";
import type { ToolDefinition } from "@/types/tools";
import type { Workflow } from "@/types/workflows";

function runDuration(run: Workflow): number | null {
  const started = run.tasks.map((task) => task.started_at).filter(Boolean).map((value) => Date.parse(value as string));
  const finished = run.tasks.map((task) => task.finished_at).filter(Boolean).map((value) => Date.parse(value as string));
  if (!started.length || !finished.length) return null;
  return Math.max(0, (Math.max(...finished) - Math.min(...started)) / 1000);
}

/**
 * One workflow run end to end: its steps, the recorded timeline of every run and step
 * change (with the worker that held the run), the tool runs and the approvals. Read only:
 * pausing, resuming, cancelling and retrying stay on the Workflows page.
 */
export function WorkflowRunTrace({ runId, summary, tools, now, onBack }: {
  runId: string;
  /** The list's copy, shown immediately; `null` when deep-linked to a run outside the list. */
  summary: Workflow | null;
  tools: ReadonlyMap<string, ToolDefinition>;
  now: Date;
  onBack?: () => void;
}) {
  const updatedAt = summary?.updated_at ?? null;
  const [detail, setDetail] = useState<{ id: string; trace: WorkflowTrace } | null>(null);
  const [error, setError] = useState<{ id: string; message: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    OperationsService.workflowTrace(runId)
      .then((trace) => { if (!cancelled) { setDetail({ id: runId, trace }); setError(null); } })
      .catch((cause) => { if (!cancelled) setError({ id: runId, message: cause instanceof OperationsApiError ? cause.message : "Unable to load this workflow run." }); });
    return () => { cancelled = true; };
  }, [runId, updatedAt]);

  const trace = detail?.id === runId ? detail.trace : null;
  const run = trace?.run ?? summary;
  const loadError = error?.id === runId ? error.message : null;

  if (run === null) {
    return loadError
      ? <Alert tone="danger">{loadError}</Alert>
      : <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading workflow run"><Skeleton className="h-5 w-24" /><Skeleton className="h-4 w-3/4" /><Skeleton className="h-16 w-full" /></div>;
  }

  const progress = runProgress(run);
  const stepNames = Object.fromEntries(run.tasks.map((task) => [task.task_id, task.name]));
  const attempts = trace ? attemptsOf(trace.transitions) : [];

  return (
    <article aria-labelledby={`run-${runId}-title`} className="flex min-w-0 flex-col gap-4">
      <header className="flex items-start gap-2">
        {onBack && (
          <IconButton label="Back to workflow runs" onClick={onBack} className="-ml-1 lg:hidden">
            <ArrowLeft aria-hidden className="h-4 w-4" />
          </IconButton>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={run.status} />
            <span className="text-[11px] text-muted-foreground">
              Workflow run{run.definition_version ? ` · version ${run.definition_version}` : ""}{run.attempt > 1 ? ` · attempt ${run.attempt}` : ""}
            </span>
          </div>
          <h2 id={`run-${runId}-title`} className="mt-2 break-words text-sm font-semibold leading-6 text-foreground">{run.name}</h2>
          <Link href={`/workflows?tab=runs&run=${encodeURIComponent(run.workflow_id)}`} className="mt-1 inline-flex items-center gap-0.5 text-[11px] text-muted-foreground hover:text-foreground">
            Manage this run in Workflows<ArrowUpRight aria-hidden className="h-3 w-3" />
          </Link>
        </div>
      </header>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-md border border-border bg-surface-2/50 p-3 sm:grid-cols-4">
        <div><dt className="text-[11px] text-muted-foreground">Steps done</dt><dd className="mt-0.5 text-xs text-foreground">{progress.completed} of {progress.total}</dd></div>
        <div><dt className="text-[11px] text-muted-foreground">Failed</dt><dd className="mt-0.5 text-xs text-foreground">{progress.failed}</dd></div>
        <div><dt className="text-[11px] text-muted-foreground">Created</dt><dd className="mt-0.5 truncate text-xs text-foreground">{new Date(run.created_at).toLocaleString()}</dd></div>
        <div><dt className="text-[11px] text-muted-foreground">Step time</dt><dd className="mt-0.5 text-xs text-foreground">{formatDuration(runDuration(run))}</dd></div>
      </dl>

      {loadError && <Alert tone="danger">{loadError}</Alert>}
      {run.status === "failed" && <Alert tone="danger"><p className="font-medium">Failed</p>{run.error && <p className="mt-1 break-words text-xs leading-5 text-foreground/85">{run.error}</p>}</Alert>}
      {run.status === "interrupted" && <Alert tone="warning"><p className="font-medium">Genesis stopped while a step that may have outside effects was running, so its outcome is unknown.</p><p className="mt-1 text-xs text-muted-foreground">It was not resumed automatically. Retry or cancel it from Workflows.</p></Alert>}
      {run.status === "waiting_approval" && <Alert tone="warning">A step is waiting for an operator decision in Approvals. The run continues on its own once it is decided.</Alert>}

      <section aria-label="Steps">
        <h3 className="mb-2 text-xs font-medium text-muted-foreground">Steps</h3>
        <StepList steps={run.tasks} tools={tools} />
      </section>

      {trace ? (
        <>
          <ToolRunsSection tasks={trace.tool_tasks} now={now} empty="No tool has run for this workflow yet." />
          <ApprovalsSection approvals={trace.approvals} now={now} />
          <TruncationNote limits={trace.truncated} />
          <section aria-label="Timeline">
            <h3 className="text-xs font-medium text-muted-foreground">Timeline{attempts.length > 1 ? ` · ${attempts.length} attempts` : ""}</h3>
            {trace.transitions.length === 0 ? (
              <p className="mt-1.5 text-xs text-muted-foreground">No changes recorded. Runs from before the timeline was stored show their current state only.</p>
            ) : (
              <ol className="mt-2 flex flex-col">
                {trace.transitions.map((change, index) => (
                  <li key={change.sequence} className="relative flex gap-3 pb-3 last:pb-0">
                    {index < trace.transitions.length - 1 && <span aria-hidden className="absolute left-[3px] top-3 h-full w-px bg-border" />}
                    <StatusDot tone={statusPresentation(change.to_status).tone} className="relative mt-1.5" />
                    <div className="min-w-0 flex-1">
                      <p className={change.step_id === null ? "break-words text-xs font-medium leading-5 text-foreground" : "break-words text-xs leading-5 text-foreground"}>
                        {describeWorkflowTransition(change, stepNames)}
                      </p>
                      {change.detail && change.to_status !== "completed" && <p className="break-words text-[11px] text-muted-foreground">{change.detail}</p>}
                      <time dateTime={change.at} className="text-[11px] text-muted-foreground">{new Date(change.at).toLocaleTimeString()}{attempts.length > 1 ? ` · attempt ${change.attempt}` : ""}</time>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      ) : !loadError && (
        <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading run history"><Skeleton className="h-3 w-2/3" /><Skeleton className="h-3 w-1/2" /><Skeleton className="h-3 w-3/5" /></div>
      )}

      <div className="flex items-center justify-between gap-2 border-t border-border pt-3 text-[11px] text-muted-foreground">
        <span>Run ID <span className="font-mono text-foreground/90">{run.workflow_id}</span></span>
        <CopyButton value={run.workflow_id} label="Copy run ID" />
      </div>
    </article>
  );
}
