"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, Clock3, History, LoaderCircle, PlayCircle, XCircle } from "lucide-react";

import { RetryControl } from "@/components/durable/retry-control";
import { describeTransition, isActive, statusText } from "@/lib/durable-work";
import { ExecutionApiError, ExecutionService } from "@/services/execution.service";
import type { Execution, ExecutionStatus, ExecutionTransition } from "@/types/executions";

const STATUS_STYLE: Record<ExecutionStatus, { tone: string; Icon: typeof Clock3 }> = {
  pending: { tone: "text-slate-300", Icon: Clock3 },
  queued: { tone: "text-sky-300", Icon: Clock3 },
  starting: { tone: "text-indigo-300", Icon: PlayCircle },
  running: { tone: "text-amber-300", Icon: LoaderCircle },
  completed: { tone: "text-emerald-300", Icon: CheckCircle2 },
  failed: { tone: "text-red-300", Icon: XCircle },
  cancelled: { tone: "text-slate-300", Icon: CircleSlash },
  interrupted: { tone: "text-orange-300", Icon: AlertTriangle },
};

function Status({ status }: { status: ExecutionStatus }) {
  const { tone, Icon } = STATUS_STYLE[status];
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${tone}`}>
      <Icon className={`h-3.5 w-3.5 ${status === "running" ? "animate-spin" : ""}`} aria-hidden="true" />
      {statusText(status)}
    </span>
  );
}

/** Recent executions from durable storage, with a timeline and server-gated retry. */
export function ExecutionInspector({ executions, onChanged }: { executions: Execution[]; onChanged: () => Promise<void> | void }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ execution: Execution; timeline: ExecutionTransition[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recent = executions.slice(0, 12);
  const selected = recent.find((item) => item.execution_id === selectedId) ?? null;
  const selectedUpdatedAt = selected?.updated_at ?? null;

  useEffect(() => {
    if (selectedId === null) return;
    let cancelled = false;
    queueMicrotask(() => {
      setLoading(true);
      setError(null);
      Promise.all([ExecutionService.get(selectedId), ExecutionService.history(selectedId)])
        .then(([execution, history]) => { if (!cancelled) setDetail({ execution, timeline: history.transitions }); })
        .catch((cause) => { if (!cancelled) setError(cause instanceof ExecutionApiError ? cause.message : "Unable to load this execution."); })
        .finally(() => { if (!cancelled) setLoading(false); });
    });
    return () => { cancelled = true; };
  }, [selectedId, selectedUpdatedAt]);

  async function retry(acknowledgeSideEffects: boolean): Promise<string | null> {
    if (detail === null) return null;
    try {
      const next = await ExecutionService.retry(detail.execution.execution_id, acknowledgeSideEffects);
      await onChanged();
      setSelectedId(next.execution_id);
      return null;
    } catch (cause) {
      return cause instanceof ExecutionApiError ? cause.message : "The retry could not be started.";
    }
  }

  return (
    <section aria-labelledby="execution-inspector-title" className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 id="execution-inspector-title" className="text-sm font-semibold text-foreground">Executions</h2>
          <p className="mt-1 text-xs text-muted-foreground">Stored durably; they survive restarts. Open one to see its timeline.</p>
        </div>
        <History className="h-4 w-4 text-primary" aria-hidden="true" />
      </div>
      {recent.length === 0 ? (
        <p className="mt-4 rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">No executions yet.</p>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <ul className="divide-y divide-border rounded-lg border border-border">
            {recent.map((execution) => (
              <li key={execution.execution_id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(execution.execution_id)}
                  aria-current={execution.execution_id === selectedId ? "true" : undefined}
                  className={`flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition-colors hover:bg-white/[0.03] ${execution.execution_id === selectedId ? "bg-primary/[0.06]" : ""}`}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-xs text-foreground">
                      {typeof execution.metadata.tool_name === "string" ? `Tool: ${execution.metadata.tool_name}` : "Agent work"}
                      {execution.attempt > 1 && <span className="ml-1.5 text-muted-foreground">· attempt {execution.attempt}</span>}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-muted-foreground">{new Date(execution.created_at).toLocaleString()}</span>
                  </span>
                  <Status status={execution.status} />
                </button>
              </li>
            ))}
          </ul>
          <div aria-live="polite">
            {selectedId === null ? (
              <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground">Select an execution to inspect it.</p>
            ) : loading && detail === null ? (
              <p className="flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground"><LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />Loading…</p>
            ) : error ? (
              <p role="alert" className="rounded-lg border border-red-400/25 bg-red-400/5 p-3 text-xs text-red-200">{error}</p>
            ) : detail ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Status status={detail.execution.status} />
                  <span className="font-mono text-[11px] text-muted-foreground">{detail.execution.execution_id}</span>
                </div>
                {detail.execution.result?.output && <p className="text-xs text-foreground">Output: <span className="font-mono">{detail.execution.result.output}</span></p>}
                {detail.execution.error && (
                  <p className="rounded-lg border border-red-400/20 bg-red-400/5 p-2.5 text-xs leading-5 text-red-100">
                    {detail.execution.error_category && <span className="mr-1 font-medium">[{detail.execution.error_category}]</span>}
                    {detail.execution.error}
                  </p>
                )}
                {detail.execution.retry_of && <p className="text-[11px] text-muted-foreground">Retry of <button type="button" className="font-mono text-primary hover:underline" onClick={() => setSelectedId(detail.execution.retry_of)}>{detail.execution.retry_of.slice(0, 8)}</button></p>}
                <ol className="space-y-1.5 border-l border-border pl-3">
                  {detail.timeline.map((step) => (
                    <li key={step.sequence} className="text-[11px] leading-4">
                      <span className="text-foreground">{describeTransition(step)}</span>
                      <time className="ml-2 text-muted-foreground">{new Date(step.at).toLocaleTimeString()}</time>
                    </li>
                  ))}
                </ol>
                {!isActive(detail.execution.status) && <RetryControl key={detail.execution.execution_id} retry={detail.execution.retry} onRetry={retry} />}
              </div>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
