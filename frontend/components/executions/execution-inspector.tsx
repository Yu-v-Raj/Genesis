"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, Wrench } from "lucide-react";

import { RetryControl } from "@/components/durable/retry-control";
import { IconButton } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { Disclosure, JsonView } from "@/components/ui/disclosure";
import { Alert, Skeleton } from "@/components/ui/feedback";
import { StatusBadge, StatusDot } from "@/components/ui/status-badge";
import { describeTransition, executionLabel, isActive, isChat } from "@/lib/durable-work";
import { errorCategoryExplanation, errorCategoryLabel, executionKind, formatDuration, kindLabel } from "@/lib/operations";
import { statusPresentation } from "@/lib/status";
import { ExecutionApiError, ExecutionService } from "@/services/execution.service";
import { ToolService } from "@/services/tool.service";
import type { Execution, ExecutionTransition } from "@/types/executions";
import type { ToolTask } from "@/types/tools";

interface StartedTool {
  name: string;
  side_effects: boolean;
}

/** Tools the checkpoint says were started (names and side-effect flags only, by design). */
function startedToolsDetail(execution: Execution): StartedTool[] {
  const started = execution.checkpoint?.tools_started;
  if (!Array.isArray(started)) return [];
  return started.map((tool) => {
    const record = tool && typeof tool === "object" ? (tool as Record<string, unknown>) : {};
    return { name: typeof record.name === "string" ? record.name : "tool", side_effects: record.side_effects !== false };
  });
}

function timestamp(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "—";
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 truncate text-xs text-foreground">{children}</dd>
    </div>
  );
}

function IdRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex items-center justify-between gap-2 py-1">
      <dt className="shrink-0 text-[11px] text-muted-foreground">{label}</dt>
      <dd className="flex min-w-0 items-center gap-1">
        <span className="truncate font-mono text-[11px] text-foreground/90">{value}</span>
        <CopyButton value={value} label={`Copy ${label.toLowerCase()}`} />
      </dd>
    </div>
  );
}

/**
 * One execution in detail: summary first, then output, tools, timeline, retry, and finally
 * the raw technical record. Retry is entirely server-gated (see RetryControl); opening an
 * execution never starts anything.
 */
export function ExecutionInspector({
  executionId,
  execution: summary,
  agentName,
  onChanged,
  onSelect,
  onBack,
}: {
  executionId: string;
  /** The list's copy, shown immediately; `null` when deep-linked to a run outside the list. */
  execution: Execution | null;
  agentName?: string;
  onChanged: () => Promise<void> | void;
  onSelect: (executionId: string) => void;
  /** Shown on narrow screens, where the inspector replaces the list. */
  onBack?: () => void;
}) {
  const updatedAt = summary?.updated_at ?? null;
  const [detail, setDetail] = useState<{ id: string; execution: Execution; timeline: ExecutionTransition[] } | null>(null);
  const [error, setError] = useState<{ id: string; message: string } | null>(null);
  const [toolTasks, setToolTasks] = useState<{ id: string; tasks: ToolTask[] | null } | null>(null);

  // Reload whenever the selection changes or the list reports a newer version of it.
  useEffect(() => {
    let cancelled = false;
    Promise.all([ExecutionService.get(executionId), ExecutionService.history(executionId)])
      .then(([execution, history]) => { if (!cancelled) { setDetail({ id: executionId, execution, timeline: history.transitions }); setError(null); } })
      .catch((cause) => { if (!cancelled) setError({ id: executionId, message: cause instanceof ExecutionApiError ? cause.message : "Unable to load this execution." }); });
    return () => { cancelled = true; };
  }, [executionId, updatedAt]);

  // Tool results live in the Tool Runtime's history (kept in memory until the backend restarts).
  useEffect(() => {
    let cancelled = false;
    ToolService.history()
      .then(({ tasks }) => { if (!cancelled) setToolTasks({ id: executionId, tasks: tasks.filter((task) => task.execution_id === executionId) }); })
      .catch(() => { if (!cancelled) setToolTasks({ id: executionId, tasks: null }); });
    return () => { cancelled = true; };
  }, [executionId, updatedAt]);

  async function retry(acknowledgeSideEffects: boolean): Promise<string | null> {
    try {
      const next = await ExecutionService.retry(executionId, acknowledgeSideEffects);
      await onChanged();
      onSelect(next.execution_id);
      return null;
    } catch (cause) {
      return cause instanceof ExecutionApiError ? cause.message : "The retry could not be started.";
    }
  }

  const current = detail?.id === executionId ? detail : null;
  const execution = current?.execution ?? summary;
  const loadError = error?.id === executionId ? error.message : null;

  if (execution === null) {
    return loadError
      ? <Alert tone="danger">{loadError}</Alert>
      : <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading execution"><Skeleton className="h-5 w-24" /><Skeleton className="h-4 w-3/4" /><Skeleton className="h-16 w-full" /></div>;
  }

  const tasks = toolTasks?.id === executionId ? toolTasks.tasks : undefined;
  const started = startedToolsDetail(execution);
  const kind = executionKind(execution);
  const output = execution.result?.output;
  const category = errorCategoryLabel(execution.error_category);

  return (
    <article aria-labelledby={`execution-${executionId}-title`} className="flex min-w-0 flex-col gap-4">
      <header className="flex items-start gap-2">
        {onBack && (
          <IconButton label="Back to executions" onClick={onBack} className="-ml-1 lg:hidden">
            <ArrowLeft aria-hidden className="h-4 w-4" />
          </IconButton>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={execution.status} />
            <span className="text-[11px] text-muted-foreground">{kindLabel(kind)}{execution.attempt > 1 ? ` · attempt ${execution.attempt}` : ""}</span>
          </div>
          <h2 id={`execution-${executionId}-title`} className="mt-2 break-words text-sm font-semibold leading-6 text-foreground">{executionLabel(execution, agentName)}</h2>
        </div>
      </header>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-md border border-border bg-surface-2/50 p-3 sm:grid-cols-4">
        <Fact label="Agent">{agentName ?? "Unknown Agent"}</Fact>
        <Fact label="Started">{timestamp(execution.started_at ?? execution.created_at)}</Fact>
        <Fact label="Finished">{timestamp(execution.finished_at)}</Fact>
        <Fact label="Duration">{formatDuration(execution.duration)}</Fact>
      </dl>

      {loadError && <Alert tone="danger">{loadError}</Alert>}

      {isActive(execution.status) && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground" role="status">
          <StatusDot tone="running" pulse /> This run is in progress{execution.current_step ? ` — ${execution.current_step}` : ""}. Details update automatically.
        </p>
      )}
      {execution.status === "failed" && (
        <Alert tone="danger">
          <p className="font-medium">{category ? `Failed: ${category}` : "Failed"}</p>
          {errorCategoryExplanation(execution.error_category) && <p className="mt-1 text-xs leading-5 text-muted-foreground">{errorCategoryExplanation(execution.error_category)}</p>}
          {execution.error && <p className="mt-1 break-words text-xs leading-5 text-foreground/85">{execution.error}</p>}
        </Alert>
      )}
      {execution.status === "interrupted" && (
        <Alert tone="warning">
          <p className="font-medium">Genesis stopped while this run was in progress, so its outcome is unknown.</p>
          {execution.error && <p className="mt-1 break-words text-xs leading-5 text-foreground/85">{execution.error}</p>}
        </Alert>
      )}
      {execution.status === "cancelled" && <p className="text-xs text-muted-foreground">This run was cancelled before it finished.</p>}

      {output && (
        <section aria-label={isChat(execution) ? "Reply" : "Output"}>
          <h3 className="text-xs font-medium text-muted-foreground">{isChat(execution) ? "Reply" : "Output"}</h3>
          <p className="mt-1.5 max-h-48 overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background p-3 text-sm leading-6 text-foreground">{output}</p>
        </section>
      )}

      {(started.length > 0 || (tasks && tasks.length > 0)) && (
        <section aria-label="Tool activity">
          <h3 className="text-xs font-medium text-muted-foreground">Tool activity</h3>
          {tasks && tasks.length > 0 ? (
            <ul className="mt-1.5 flex flex-col gap-1.5">
              {tasks.map((task) => (
                <li key={task.task_id} className="rounded-md border border-border bg-surface-2/50">
                  <div className="flex items-center justify-between gap-2 px-3 py-2">
                    <span className="flex min-w-0 items-center gap-2 text-xs text-foreground"><Wrench aria-hidden className="h-3.5 w-3.5 text-muted-foreground" /><span className="truncate">{task.tool_name}</span></span>
                    <span className="flex shrink-0 items-center gap-2 text-[11px] text-muted-foreground">{formatDuration(task.result?.duration)}<StatusBadge status={task.result?.status ?? task.status} /></span>
                  </div>
                  {task.result && (task.result.output !== null || task.result.error) && (
                    <Disclosure summary="Result" className="mx-2 mb-2">
                      {task.result.error && <p className="mb-2 break-words text-xs text-danger">{task.result.error}</p>}
                      {task.result.output !== null && <JsonView value={task.result.output} />}
                    </Disclosure>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <>
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {started.map((tool, index) => (
                  <li key={`${tool.name}-${index}`} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-2/50 px-2 py-1 text-xs text-foreground">
                    <Wrench aria-hidden className="h-3 w-3 text-muted-foreground" />{tool.name}
                    {tool.side_effects && <span className="text-[10px] text-warning">may change things outside Genesis</span>}
                  </li>
                ))}
              </ul>
              {tasks !== undefined && (
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  {tasks === null ? "Tool results couldn't be loaded." : "Tool results are kept only until the backend restarts, so they're no longer available for this run."}
                </p>
              )}
            </>
          )}
        </section>
      )}

      <section aria-label="Timeline">
        <h3 className="text-xs font-medium text-muted-foreground">Timeline</h3>
        {current === null && !loadError ? (
          <div className="mt-2 flex flex-col gap-2" aria-busy="true"><Skeleton className="h-3 w-2/3" /><Skeleton className="h-3 w-1/2" /><Skeleton className="h-3 w-3/5" /></div>
        ) : current && current.timeline.length > 0 ? (
          <ol className="mt-2 flex flex-col">
            {current.timeline.map((step, index) => (
              <li key={step.sequence} className="relative flex gap-3 pb-3 last:pb-0">
                {index < current.timeline.length - 1 && <span aria-hidden className="absolute left-[3px] top-3 h-full w-px bg-border" />}
                <StatusDot tone={statusPresentation(step.to_status).tone} className="relative mt-1.5" />
                <div className="min-w-0 flex-1">
                  <p className="break-words text-xs leading-5 text-foreground">{describeTransition(step)}</p>
                  <time dateTime={step.at} className="text-[11px] text-muted-foreground">{new Date(step.at).toLocaleTimeString()}</time>
                </div>
              </li>
            ))}
          </ol>
        ) : current ? <p className="mt-1.5 text-xs text-muted-foreground">No state changes recorded.</p> : null}
      </section>

      {execution.retry_of && (
        <p className="text-xs text-muted-foreground">
          Retry of an earlier run.{" "}
          <button type="button" onClick={() => onSelect(execution.retry_of as string)} className="text-accent hover:underline">Open the original</button>
        </p>
      )}

      {!isActive(execution.status) && <RetryControl key={executionId} retry={execution.retry} onRetry={retry} />}

      <Disclosure summary="Technical details">
        <dl className="divide-y divide-border">
          <IdRow label="Execution ID" value={execution.execution_id} />
          <IdRow label="Agent ID" value={execution.agent_id} />
          <IdRow label="Session ID" value={typeof execution.metadata.session_id === "string" ? execution.metadata.session_id : null} />
          <IdRow label="Retry of" value={execution.retry_of} />
          <IdRow label="Error category" value={execution.error_category} />
        </dl>
        <div className="mt-3 flex flex-col gap-3">
          <div><p className="mb-1 text-[11px] text-muted-foreground">Metadata</p><JsonView value={execution.metadata} /></div>
          <div><p className="mb-1 text-[11px] text-muted-foreground">Checkpoint</p><JsonView value={execution.checkpoint} /></div>
          {execution.result && <div><p className="mb-1 text-[11px] text-muted-foreground">Result</p><JsonView value={execution.result} /></div>}
        </div>
      </Disclosure>

    </article>
  );
}
