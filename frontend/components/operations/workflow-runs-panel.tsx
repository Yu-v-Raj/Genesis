"use client";

import { useCallback, useEffect, useState } from "react";
import { Search, Workflow as WorkflowIcon } from "lucide-react";

import { WorkflowRunTrace } from "@/components/operations/workflow-run-trace";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/field";
import { StatusBadge } from "@/components/ui/status-badge";
import { relativeTime } from "@/lib/operations";
import { mergeById } from "@/lib/traces";
import { RUN_FILTERS, filterRuns, runProgress, type RunFilter } from "@/lib/workflows";
import { cn } from "@/lib/utils";
import { ToolService } from "@/services/tool.service";
import { WorkflowApiError, WorkflowService } from "@/services/workflow.service";
import type { ToolDefinition } from "@/types/tools";
import type { Workflow } from "@/types/workflows";

const PAGE = 50;

/**
 * Workflow runs, discoverable next to Agent executions without being copied into them:
 * the list reads the Workflow runtime's own runs, newest first, and pages back in time.
 */
export function WorkflowRunsPanel({ selectedId, onSelect, onBack, refreshKey, now }: {
  selectedId: string | null;
  onSelect: (runId: string) => void;
  onBack: () => void;
  /** Changes when a live workflow event arrives, to refresh the newest page. */
  refreshKey: string | null;
  now: Date;
}) {
  const [runs, setRuns] = useState<Workflow[] | null>(null);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tools, setTools] = useState<ReadonlyMap<string, ToolDefinition>>(new Map());
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<RunFilter>("all");

  const loadNewest = useCallback(async () => {
    try {
      const page = await WorkflowService.list(null, PAGE);
      setRuns((current) => mergeById(current ?? [], page.workflows, (run) => run.workflow_id, (run) => run.created_at));
      setNextBefore((current) => current ?? page.next_before ?? null);
      setError(null);
    } catch (cause) {
      setError(cause instanceof WorkflowApiError ? cause.message : "Workflow runs couldn't be loaded.");
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void loadNewest()); }, [loadNewest, refreshKey]);
  useEffect(() => {
    let active = true;
    ToolService.list().then(({ tools: list }) => { if (active) setTools(new Map(list.map((tool) => [tool.name, tool]))); }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  async function loadOlder() {
    if (!nextBefore) return;
    setLoadingOlder(true);
    try {
      const page = await WorkflowService.list(nextBefore, PAGE);
      setRuns((current) => mergeById(current ?? [], page.workflows, (run) => run.workflow_id, (run) => run.created_at));
      setNextBefore(page.next_before ?? null);
    } catch (cause) {
      setError(cause instanceof WorkflowApiError ? cause.message : "Older runs couldn't be loaded.");
    } finally {
      setLoadingOlder(false);
    }
  }

  const visible = runs ? filterRuns(runs, query, filter) : [];
  const selected = selectedId ? runs?.find((run) => run.workflow_id === selectedId) ?? null : null;

  return (
    <div className="flex flex-col gap-4">
      {error && <Alert tone={runs === null ? "danger" : "warning"} action={<Button size="sm" onClick={() => void loadNewest()}>Try again</Button>}>{error}</Alert>}
      <div className={cn("flex flex-col gap-2 sm:flex-row sm:items-center", selectedId && "hidden lg:flex")}>
        <div className="relative sm:w-64">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name or ID" aria-label="Search workflow runs" className="pl-8" />
        </div>
        <Select aria-label="Run status" value={filter} onChange={(event) => setFilter(event.target.value as RunFilter)} className="sm:w-44">
          {RUN_FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </Select>
        {runs && <p className="text-xs text-muted-foreground sm:ml-auto" aria-live="polite">{visible.length} of {runs.length} loaded runs{nextBefore ? " (older runs available)" : ""}</p>}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className={cn("min-w-0", selectedId && "hidden lg:block")}>
          {runs === null ? (
            <div className="flex flex-col gap-2" aria-busy="true">{Array.from({ length: 5 }, (_, index) => <Skeleton key={index} className="h-14 w-full" />)}</div>
          ) : runs.length === 0 ? (
            <EmptyState icon={WorkflowIcon} title="No workflow runs yet" description="Runs appear here once a workflow is started, with every step change recorded." />
          ) : visible.length === 0 ? (
            <EmptyState icon={Search} title="No runs match" action={<Button size="sm" onClick={() => { setQuery(""); setFilter("all"); }}>Clear filters</Button>} />
          ) : (
            <div className="overflow-hidden rounded-lg border border-border bg-surface">
              <ul aria-label="Workflow runs" className="max-h-[40rem] divide-y divide-border overflow-y-auto">
                {visible.map((run) => {
                  const progress = runProgress(run);
                  const isSelected = run.workflow_id === selectedId;
                  return (
                    <li key={run.workflow_id}>
                      <button type="button" data-run-id={run.workflow_id} onClick={() => onSelect(run.workflow_id)} aria-current={isSelected ? "true" : undefined}
                        className={cn("relative flex w-full flex-col gap-1.5 px-4 py-3 text-left transition-colors hover:bg-white/[0.025]", isSelected && "bg-white/[0.05]")}>
                        {isSelected && <span aria-hidden className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" />}
                        <span className="flex items-start justify-between gap-3">
                          <span className="line-clamp-2 min-w-0 break-words text-sm text-foreground">{run.name}</span>
                          <StatusBadge status={run.status} className="shrink-0" />
                        </span>
                        <span className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                          <span>{progress.completed}/{progress.total} steps</span>
                          <span aria-hidden>·</span>
                          <time dateTime={run.created_at} title={new Date(run.created_at).toLocaleString()}>{relativeTime(run.created_at, now)}</time>
                          {run.attempt > 1 && <><span aria-hidden>·</span><span>attempt {run.attempt}</span></>}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              {nextBefore && (
                <button type="button" onClick={() => void loadOlder()} disabled={loadingOlder} className="w-full border-t border-border py-2 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-60">
                  {loadingOlder ? "Loading…" : "Load older runs"}
                </button>
              )}
            </div>
          )}
        </div>

        <section id="workflow-run-detail" tabIndex={-1} aria-label="Workflow run details" className={cn("min-w-0 rounded-lg border border-border bg-surface p-4 focus:outline-none sm:p-5", !selectedId && "hidden lg:block")}>
          {selectedId ? (
            <WorkflowRunTrace key={selectedId} runId={selectedId} summary={selected} tools={tools} now={now} onBack={onBack} />
          ) : (
            <div className="flex h-full min-h-48 flex-col items-center justify-center text-center">
              <WorkflowIcon aria-hidden className="h-5 w-5 text-muted-foreground" />
              <p className="mt-2 text-sm text-foreground">Select a run to trace it</p>
              <p className="mt-1 max-w-xs text-xs text-muted-foreground">See every step change, the tool runs, approvals and which worker ran it.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
