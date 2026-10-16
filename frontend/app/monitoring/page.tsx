"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Activity, Search, X } from "lucide-react";

import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { ExecutionInspector } from "@/components/executions/execution-inspector";
import { DurableEvents } from "@/components/operations/durable-events";
import { EventStream } from "@/components/operations/event-stream";
import { LogViewer } from "@/components/operations/log-viewer";
import { SystemPanel } from "@/components/operations/system-panel";
import { WorkflowRunsPanel } from "@/components/operations/workflow-runs-panel";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge, StatusDot } from "@/components/ui/status-badge";
import { Tabs, tabPanelProps, type TabItem } from "@/components/ui/tabs";
import { useMonitoring } from "@/hooks/use-monitoring";
import { useNow } from "@/hooks/use-now";
import { executionLabel } from "@/lib/durable-work";
import {
  EMPTY_FILTERS, STATUS_FILTER_OPTIONS, countLabel, errorCategoryLabel, executionKind, filterExecutions, filtersFromParams,
  formatDuration, hasActiveFilters, kindLabel, operationsQuery, relativeTime, summarizeExecutions, type ExecutionFilters, type StatusFilter,
} from "@/lib/operations";
import { statusPresentation } from "@/lib/status";
import { isDurableEventType, mergeById } from "@/lib/traces";
import { cn } from "@/lib/utils";
import { ExecutionApiError, ExecutionService } from "@/services/execution.service";
import type { Execution } from "@/types/executions";

type Tab = "executions" | "workflows" | "events" | "logs" | "system";
const TABS = new Set<Tab>(["executions", "workflows", "events", "logs", "system"]);
const PAGE = 50;
const TAB_PREFIX = "operations";

export default function OperationsPage() {
  // Filters and the selected run live in the URL (shareable, back/forward aware), which
  // needs a Suspense boundary for useSearchParams on this statically rendered route.
  return (
    <Suspense fallback={<OperationsSkeleton />}>
      <Operations />
    </Suspense>
  );
}

function OperationsSkeleton() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8" aria-busy="true">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-96 w-full" />
    </div>
  );
}

function Operations() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { data, loading, error, connectionStatus, retry } = useMonitoring({ eventLimit: 1000 });
  const now = useNow();

  const filters = filtersFromParams(params);
  const tabParam = params.get("tab") as Tab | null;
  const tab: Tab = tabParam && TABS.has(tabParam) ? tabParam : "executions";
  const selectedId = params.get("execution");
  const selectedRunId = params.get("run");
  const [query, setQuery] = useState(filters.query);
  const [limit, setLimit] = useState(PAGE);
  const [eventView, setEventView] = useState<"stored" | "live">("stored");
  // Executions older than the newest page, loaded on request.
  const [older, setOlder] = useState<{ executions: Execution[]; nextBefore: string | null; loading: boolean; error: string | null }>({ executions: [], nextBefore: null, loading: false, error: null });

  function go(view: Partial<ExecutionFilters> & { tab?: Tab; execution?: string | null; run?: string | null }, mode: "push" | "replace" = "replace") {
    const next = { ...filters, query, tab, execution: selectedId, run: selectedRunId, ...view };
    router[mode](`${pathname}${operationsQuery(next)}`, { scroll: false });
  }

  const agentNames: Record<string, string> = Object.fromEntries((data?.agents ?? []).map((agent) => [agent.id, agent.name]));
  const executions = data ? mergeById(data.executions, older.executions, (item) => item.execution_id, (item) => item.created_at) : [];
  const olderCursor = older.executions.length ? older.nextBefore : data?.executionsNextBefore ?? null;
  const latestDurableEvent = data?.events.find((event) => isDurableEventType(event.event_type))?.id ?? null;
  const latestWorkflowEvent = data?.events.find((event) => event.event_type.startsWith("workflow."))?.id ?? null;

  async function loadOlderExecutions() {
    if (!olderCursor) return;
    setOlder((current) => ({ ...current, loading: true, error: null }));
    try {
      const page = await ExecutionService.list(olderCursor);
      setOlder((current) => ({ executions: [...current.executions, ...page.executions], nextBefore: page.next_before ?? null, loading: false, error: null }));
    } catch (cause) {
      setOlder((current) => ({ ...current, loading: false, error: cause instanceof ExecutionApiError ? cause.message : "Older runs couldn't be loaded." }));
    }
  }
  const visible = filterExecutions(executions, { ...filters, query }, agentNames);
  const kinds = [...new Set(executions.map(executionKind))].sort();
  const summary = data ? summarizeExecutions(executions, now) : null;
  const selected = selectedId ? executions.find((execution) => execution.execution_id === selectedId) ?? null : null;
  const filtered = hasActiveFilters({ ...filters, query });

  // On narrow screens the inspector replaces the list, so focus follows the swap: into the
  // inspector on open, and back to the run's row on return. Wide screens keep focus in place.
  const pendingFocus = useRef<{ to: "detail" } | { to: "row"; id: string } | null>(null);
  useEffect(() => {
    const target = pendingFocus.current;
    pendingFocus.current = null;
    if (!target || window.matchMedia("(min-width: 1024px)").matches) return;
    const element = target.to === "detail" ? document.getElementById("execution-detail") : document.querySelector<HTMLElement>(`[data-execution-id="${CSS.escape(target.id)}"]`);
    element?.focus();
  }, [selectedId]);

  function select(execution: Execution) {
    pendingFocus.current = { to: "detail" };
    go({ execution: execution.execution_id }, "push");
  }

  function backToList() {
    if (selectedId) pendingFocus.current = { to: "row", id: selectedId };
    go({ execution: null });
  }

  const tabs: TabItem<Tab>[] = [
    { value: "executions", label: "Executions", badge: data ? countLabel(executions.length, olderCursor !== null) : undefined },
    { value: "workflows", label: "Workflow runs" },
    { value: "events", label: "Events" },
    { value: "logs", label: "Logs" },
    { value: "system", label: "System" },
  ];

  const summaryItems: { label: string; value: string; detail: string; filter: StatusFilter; tone: "running" | "success" | "danger" | "neutral" }[] = summary ? [
    { label: "In progress", value: String(summary.active), detail: "Running or waiting to run", filter: "active", tone: summary.active ? "running" : "neutral" },
    { label: "Completed", value: countLabel(summary.completed24h, summary.capped), detail: "Last 24 hours", filter: "completed", tone: "success" },
    { label: "Needs attention", value: countLabel(summary.attention24h, summary.capped), detail: "Failed or interrupted, last 24 hours", filter: "attention", tone: summary.attention24h ? "danger" : "neutral" },
    { label: "All runs", value: countLabel(summary.last24h, summary.capped), detail: "Started in the last 24 hours", filter: "all", tone: "neutral" },
  ] : [];

  const connection = statusPresentation(connectionStatus);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
      {data && <RealtimeNotifications events={data.events.slice(0, 1)} />}
      <PageHeader
        title="Operations"
        description="Trace Agent runs and workflow runs end to end, follow stored activity and check service health."
        meta={
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground" role="status">
            <span className="inline-flex items-center gap-1.5"><StatusDot tone={connection.tone} pulse={connectionStatus === "connecting"} />{connectionStatus === "connected" ? "Live updates on" : connectionStatus === "connecting" ? "Connecting to live updates…" : "Live updates disconnected — reconnecting"}</span>
            {data?.lastHeartbeat && <span>Heartbeat {relativeTime(data.lastHeartbeat, now)}</span>}
          </p>
        }
      />

      {error && data === null ? (
        <Alert tone="danger" action={<Button size="sm" onClick={() => void retry()} loading={loading}>Try again</Button>}>
          <p className="font-medium">Operations data couldn&apos;t be loaded.</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{error}</p>
        </Alert>
      ) : (
        <>
          {error && <Alert tone="warning" action={<Button size="sm" onClick={() => void retry()} loading={loading}>Refresh</Button>}>Couldn&apos;t refresh: {error}</Alert>}

          <section aria-label="Run summary" className="grid grid-cols-2 overflow-hidden rounded-lg border border-border bg-border gap-px lg:grid-cols-4">
            {summary === null
              ? Array.from({ length: 4 }, (_, index) => <div key={index} className="bg-surface p-4"><Skeleton className="h-3 w-20" /><Skeleton className="mt-3 h-6 w-10" /></div>)
              : summaryItems.map((item) => (
                <button key={item.label} type="button" onClick={() => { setLimit(PAGE); go({ tab: "executions", status: item.filter }); }} aria-pressed={tab === "executions" && filters.status === item.filter}
                  className={cn("bg-surface p-4 text-left transition-colors hover:bg-surface-2", tab === "executions" && filters.status === item.filter && "bg-surface-2")}>
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><StatusDot tone={item.tone} />{item.label}</span>
                  <span className="mt-1.5 block text-2xl font-semibold tabular-nums tracking-tight text-foreground">{item.value}</span>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">{item.detail}</span>
                </button>
              ))}
          </section>

          <div>
            <Tabs idPrefix={TAB_PREFIX} label="Operations views" items={tabs} value={tab} onChange={(value) => go({ tab: value })} />
            <div {...tabPanelProps(TAB_PREFIX, tab)} className="pt-5 focus:outline-none">
              {data === null ? (
                <div className="flex flex-col gap-2" aria-busy="true">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-14 w-full" />)}</div>
              ) : tab === "workflows" ? (
                <WorkflowRunsPanel
                  selectedId={selectedRunId}
                  onSelect={(id) => go({ run: id }, "push")}
                  onBack={() => go({ run: null })}
                  refreshKey={latestWorkflowEvent}
                  now={now}
                />
              ) : tab === "events" ? (
                <div className="flex flex-col gap-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div role="group" aria-label="Event source" className="inline-flex w-fit rounded-md border border-border p-0.5">
                      {([["stored", "Stored history"], ["live", "Live, this session"]] as const).map(([value, label]) => (
                        <button key={value} type="button" aria-pressed={eventView === value} onClick={() => setEventView(value)}
                          className={cn("h-7 rounded px-2.5 text-xs font-medium transition-colors", eventView === value ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:text-foreground")}>
                          {label}
                        </button>
                      ))}
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      {eventView === "stored"
                        ? "Run, workflow, tool, approval and model-call events, kept across restarts."
                        : "Everything the server has published since it started, including Agent, memory and system events."}
                    </p>
                  </div>
                  {eventView === "stored"
                    ? <DurableEvents agentNames={agentNames} now={now} refreshKey={latestDurableEvent} />
                    : <EventStream events={data.events} agentNames={agentNames} now={now} />}
                </div>
              ) : tab === "logs" ? (
                <LogViewer events={data.events} />
              ) : tab === "system" ? (
                <SystemPanel data={data} connectionStatus={connectionStatus} now={now} />
              ) : (
                <div className="flex flex-col gap-4">
                  <div className={cn("flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center", selectedId && "hidden lg:flex")}>
                    <div className="relative sm:w-64">
                      <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <Input value={query} onChange={(event) => { setQuery(event.target.value); setLimit(PAGE); }} placeholder="Search message, Agent or ID" aria-label="Search executions" className="pl-8" />
                    </div>
                    <Select aria-label="Status" value={filters.status} onChange={(event) => { setLimit(PAGE); go({ status: event.target.value as StatusFilter }); }} className="sm:w-44">
                      {STATUS_FILTER_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </Select>
                    <Select aria-label="Agent" value={filters.agentId ?? ""} onChange={(event) => { setLimit(PAGE); go({ agentId: event.target.value || null }); }} className="sm:w-48">
                      <option value="">All Agents</option>
                      {data.agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
                    </Select>
                    <Select aria-label="Kind" value={filters.kind ?? ""} onChange={(event) => { setLimit(PAGE); go({ kind: event.target.value || null }); }} className="sm:w-40">
                      <option value="">All kinds</option>
                      {kinds.map((kind) => <option key={kind} value={kind}>{kindLabel(kind)}</option>)}
                    </Select>
                    {filtered && (
                      <Button size="sm" variant="ghost" icon={<X aria-hidden className="h-3.5 w-3.5" />} onClick={() => { setQuery(""); setLimit(PAGE); go({ ...EMPTY_FILTERS }); }}>
                        Clear filters
                      </Button>
                    )}
                    <p className="text-xs text-muted-foreground sm:ml-auto" aria-live="polite">
                      {filtered ? `${visible.length} of ${executions.length} loaded runs` : `${executions.length} runs`}
                      {olderCursor && " (older runs available)"}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
                    <div className={cn("min-w-0", selectedId && "hidden lg:block")}>
                      {executions.length === 0 ? (
                        <EmptyState icon={Activity} title="No runs yet" description="Every chat turn and Agent task is recorded here, with its timeline and outcome." />
                      ) : visible.length === 0 ? (
                        <EmptyState icon={Search} title="No runs match these filters" action={<Button size="sm" onClick={() => { setQuery(""); go({ ...EMPTY_FILTERS }); }}>Clear filters</Button>} />
                      ) : (
                        <div className="overflow-hidden rounded-lg border border-border bg-surface">
                          <ul aria-label="Executions" className="max-h-[40rem] divide-y divide-border overflow-y-auto">
                            {visible.slice(0, limit).map((execution) => (
                              <ExecutionRow key={execution.execution_id} execution={execution} agentName={agentNames[execution.agent_id]} selected={execution.execution_id === selectedId} now={now} onSelect={select} />
                            ))}
                          </ul>
                          {visible.length > limit ? (
                            <button type="button" onClick={() => setLimit((value) => value + PAGE)} className="w-full border-t border-border py-2 text-xs text-muted-foreground transition-colors hover:text-foreground">
                              Show more ({visible.length - limit} older)
                            </button>
                          ) : olderCursor && (
                            <button type="button" onClick={() => void loadOlderExecutions()} disabled={older.loading} className="w-full border-t border-border py-2 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-60">
                              {older.loading ? "Loading…" : "Load older runs from history"}
                            </button>
                          )}
                          {older.error && <p role="alert" className="border-t border-border px-4 py-2 text-xs text-danger">{older.error}</p>}
                        </div>
                      )}
                    </div>

                    <section id="execution-detail" tabIndex={-1} aria-label="Execution details" className={cn("min-w-0 rounded-lg border border-border bg-surface p-4 focus:outline-none sm:p-5", !selectedId && "hidden lg:block")}>
                      {selectedId ? (
                        <ExecutionInspector
                          key={selectedId}
                          executionId={selectedId}
                          execution={selected}
                          agentName={selected ? agentNames[selected.agent_id] : undefined}
                          onChanged={retry}
                          onSelect={(id) => go({ execution: id }, "push")}
                          onBack={backToList}
                        />
                      ) : (
                        <div className="flex h-full min-h-48 flex-col items-center justify-center text-center">
                          <Activity aria-hidden className="h-5 w-5 text-muted-foreground" />
                          <p className="mt-2 text-sm text-foreground">Select a run to inspect it</p>
                          <p className="mt-1 max-w-xs text-xs text-muted-foreground">See its timeline, tool activity, output and errors, and retry it when that&apos;s safe.</p>
                        </div>
                      )}
                    </section>
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ExecutionRow({ execution, agentName, selected, now, onSelect }: { execution: Execution; agentName?: string; selected: boolean; now: Date; onSelect: (execution: Execution) => void }) {
  const failure = execution.status === "failed" || execution.status === "interrupted" ? errorCategoryLabel(execution.error_category) : null;
  return (
    <li>
      <button type="button" data-execution-id={execution.execution_id} onClick={() => onSelect(execution)} aria-current={selected ? "true" : undefined}
        className={cn("relative flex w-full flex-col gap-1.5 px-4 py-3 text-left transition-colors hover:bg-white/[0.025]", selected && "bg-white/[0.05]")}>
        {selected && <span aria-hidden className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" />}
        <span className="flex items-start justify-between gap-3">
          <span className="line-clamp-2 min-w-0 break-words text-sm text-foreground">{executionLabel(execution, agentName)}</span>
          <StatusBadge status={execution.status} className="shrink-0" />
        </span>
        <span className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
          <span>{kindLabel(executionKind(execution))}</span>
          <span aria-hidden>·</span>
          <time dateTime={execution.created_at} title={new Date(execution.created_at).toLocaleString()}>{relativeTime(execution.created_at, now)}</time>
          {execution.duration !== null && <><span aria-hidden>·</span><span>{formatDuration(execution.duration)}</span></>}
          {execution.attempt > 1 && <><span aria-hidden>·</span><span>attempt {execution.attempt}</span></>}
          {failure && <><span aria-hidden>·</span><span className="text-danger">{failure}</span></>}
        </span>
      </button>
    </li>
  );
}
