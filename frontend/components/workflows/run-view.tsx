"use client";

import { ArrowLeft, Pause, Play, Square, Trash2 } from "lucide-react";

import { RetryControl } from "@/components/durable/retry-control";
import { StepList } from "@/components/workflows/step-list";
import { Button, IconButton } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { Disclosure, JsonView } from "@/components/ui/disclosure";
import { Alert } from "@/components/ui/feedback";
import { StatusBadge } from "@/components/ui/status-badge";
import { relativeTime } from "@/lib/operations";
import { runActions, runProgress } from "@/lib/workflows";
import type { ToolDefinition } from "@/types/tools";
import type { Workflow } from "@/types/workflows";

export type RunRequest = "start" | "pause" | "resume" | "cancel" | "delete";

const STATUS_NOTES: Partial<Record<Workflow["status"], string>> = {
  created: "Not started yet. Nothing runs until you start it.",
  queued: "Waiting for the server's workflow worker to pick it up.",
  running: "Running on the server. Leaving this page doesn't stop it.",
  paused: "Paused: steps already running finish, but no new steps start until you resume.",
  cancelled: "Cancelled. Steps that hadn't finished were cancelled.",
};

/** One run, entirely from its own record: status, steps, timings, results and actions. */
export function RunView({ run, tools, now, pending, actionError, onRequest, onRetry, onBack, onOpenDefinition }: {
  run: Workflow;
  tools: ReadonlyMap<string, ToolDefinition>;
  now: Date;
  pending: boolean;
  /** The last failed action on this run, shown next to the actions. */
  actionError: string | null;
  onRequest: (action: RunRequest) => void;
  onRetry: (acknowledgeSideEffects: boolean) => Promise<string | null>;
  onBack: () => void;
  onOpenDefinition: (() => void) | null;
}) {
  const progress = runProgress(run);
  const actions = runActions(run.status);

  return (
    <article aria-labelledby="run-title" className="flex min-w-0 flex-col gap-4">
      <header className="flex items-start gap-2">
        <IconButton label="Back" onClick={onBack} className="-ml-1 lg:hidden"><ArrowLeft aria-hidden className="h-4 w-4" /></IconButton>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="run-title" className="break-words text-base font-semibold text-foreground">{run.name}</h2>
            <StatusBadge status={run.status} />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Run{run.definition_version ? ` of version ${run.definition_version}` : ""}{run.attempt > 1 ? ` · attempt ${run.attempt}` : ""} · created {relativeTime(run.created_at, now)} · updated {relativeTime(run.updated_at, now)}
            {onOpenDefinition && <> · <button type="button" onClick={onOpenDefinition} className="text-accent hover:underline">Open the saved workflow</button></>}
          </p>
        </div>
      </header>

      <p className="text-sm text-foreground" aria-live="polite">
        {progress.completed} of {progress.total} step{progress.total === 1 ? "" : "s"} completed
        {progress.running ? ` · ${progress.running} in progress` : ""}{progress.failed ? ` · ${progress.failed} failed or interrupted` : ""}
      </p>

      {STATUS_NOTES[run.status] && <p className="text-xs text-muted-foreground">{STATUS_NOTES[run.status]}</p>}
      {run.status === "failed" && <Alert tone="danger"><p className="font-medium">The run failed.</p>{run.error && <p className="mt-0.5 break-words text-xs text-muted-foreground">{run.error}</p>}<p className="mt-0.5 text-xs text-muted-foreground">Steps that depended on a failed step were blocked.</p></Alert>}
      {run.status === "interrupted" && <Alert tone="warning"><p className="font-medium">Genesis stopped while a step was running, and that step may already have had effects.</p>{run.error && <p className="mt-0.5 break-words text-xs text-muted-foreground">{run.error}</p>}</Alert>}

      {(actions.some((action) => action !== "retry") || actionError) && (
        <div className="flex flex-wrap items-center gap-2">
          {actions.includes("start") && <Button variant="primary" size="sm" onClick={() => onRequest("start")} loading={pending} icon={<Play aria-hidden className="h-3.5 w-3.5" />}>Start…</Button>}
          {actions.includes("pause") && <Button size="sm" onClick={() => onRequest("pause")} loading={pending} icon={<Pause aria-hidden className="h-3.5 w-3.5" />}>Pause</Button>}
          {actions.includes("resume") && <Button size="sm" onClick={() => onRequest("resume")} loading={pending} icon={<Play aria-hidden className="h-3.5 w-3.5" />}>Resume</Button>}
          {actions.includes("cancel") && <Button size="sm" variant="ghost" onClick={() => onRequest("cancel")} disabled={pending} icon={<Square aria-hidden className="h-3.5 w-3.5" />}>Cancel run…</Button>}
          {actions.includes("delete") && <Button size="sm" variant="ghost" onClick={() => onRequest("delete")} disabled={pending} icon={<Trash2 aria-hidden className="h-3.5 w-3.5" />} className="text-danger hover:text-danger">Delete…</Button>}
          {actionError && <p role="alert" className="w-full text-xs text-danger">{actionError}</p>}
        </div>
      )}
      {actions.includes("retry") && <RetryControl key={`${run.workflow_id}-${run.attempt}`} retry={run.retry} onRetry={onRetry} />}

      <section aria-label="Step timeline" className="flex flex-col gap-2 border-t border-border pt-4">
        <h3 className="text-xs font-medium uppercase tracking-wider text-subtle">Steps</h3>
        <StepList steps={run.tasks} tools={tools} />
      </section>

      <Disclosure summary="Technical details">
        <dl className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs">
          <dt className="text-muted-foreground">Run ID</dt>
          <dd className="flex min-w-0 items-center gap-1"><span className="truncate font-mono text-[11px] text-foreground">{run.workflow_id}</span><CopyButton value={run.workflow_id} label="Copy run ID" /></dd>
          <dt className="text-muted-foreground">Saved workflow</dt>
          <dd className="truncate font-mono text-[11px] text-foreground">{run.definition_id ? `${run.definition_id} (v${run.definition_version})` : "None"}</dd>
          <dt className="text-muted-foreground">Created</dt><dd className="text-foreground">{new Date(run.created_at).toLocaleString()}</dd>
          <dt className="text-muted-foreground">Updated</dt><dd className="text-foreground">{new Date(run.updated_at).toLocaleString()}</dd>
          <dt className="text-muted-foreground">Metadata</dt><dd>{Object.keys(run.metadata).length ? <JsonView value={run.metadata} /> : <span className="text-foreground">None</span>}</dd>
        </dl>
      </Disclosure>
    </article>
  );
}
