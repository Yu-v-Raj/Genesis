"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus, Search, Workflow as WorkflowIcon, X } from "lucide-react";

import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { DefinitionView } from "@/components/workflows/definition-view";
import { RunView, type RunRequest } from "@/components/workflows/run-view";
import { WorkflowBuilder } from "@/components/workflows/workflow-builder";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, tabPanelProps, type TabItem } from "@/components/ui/tabs";
import { useNow } from "@/hooks/use-now";
import { useRealtime } from "@/hooks/use-realtime";
import { useWorkflows } from "@/hooks/use-workflows";
import { relativeTime } from "@/lib/operations";
import { toolLabel } from "@/lib/tools";
import { cn } from "@/lib/utils";
import { RUN_FILTERS, filterDefinitions, filterRuns, runProgress, runsOf, toolsUsed, type RunFilter } from "@/lib/workflows";
import { ToolService } from "@/services/tool.service";
import type { ToolDefinition } from "@/types/tools";
import type { StoredWorkflowDefinition, Workflow } from "@/types/workflows";

type Tab = "workflows" | "runs";
const TAB_PREFIX = "workflows";

/** A consequential action waiting for confirmation, with the server's refusal if it failed. */
type Pending =
  | { kind: "run-definition"; definition: StoredWorkflowDefinition; error: string | null }
  | { kind: "start" | "cancel" | "delete"; run: Workflow; error: string | null };

export default function WorkflowsPage() {
  // The tab, saved workflow and run live in the URL (?tab=runs&workflow=…&run=…).
  return (
    <Suspense fallback={<div className="mx-auto max-w-6xl space-y-4 px-4 py-6 sm:px-6 sm:py-8" aria-busy="true"><Skeleton className="h-8 w-40" /><Skeleton className="h-80 w-full" /></div>}>
      <Workflows />
    </Suspense>
  );
}

/** `?create=1` (used by the command palette) opens the builder, then drops the parameter. */
function CreateFromLink({ onCreate }: { onCreate: () => void }) {
  const requested = useSearchParams().get("create") === "1";
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    if (!requested) return;
    onCreate();
    const params = new URLSearchParams(window.location.search);
    params.delete("create");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [requested, onCreate, router, pathname]);
  return null;
}

function Workflows() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const realtime = useRealtime();
  const state = useWorkflows(realtime);
  const now = useNow();
  const [tools, setTools] = useState<Map<string, ToolDefinition> | null>(null);
  const [query, setQuery] = useState("");
  const [runFilter, setRunFilter] = useState<RunFilter>("all");
  const [building, setBuilding] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [actionErrors, setActionErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const confirming = useRef(false);

  useEffect(() => {
    let active = true;
    ToolService.list().then(({ tools: list }) => { if (active) setTools(new Map(list.map((tool) => [tool.name, tool]))); }).catch(() => { if (active) setTools(new Map()); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const tab: Tab = params.get("tab") === "runs" ? "runs" : "workflows";
  const definitionId = params.get("workflow");
  const runId = params.get("run");
  const definition = state.definitions.find((item) => item.definition_id === definitionId) ?? null;
  const run = state.runs.find((item) => item.workflow_id === runId) ?? null;
  const toolMap = tools ?? new Map<string, ToolDefinition>();
  const detailOpen = run !== null || (tab === "workflows" && definition !== null);

  function go(next: { tab?: Tab; workflow?: string | null; run?: string | null }, mode: "push" | "replace" = "push") {
    const search = new URLSearchParams();
    const nextTab = next.tab ?? tab;
    const workflow = next.workflow !== undefined ? next.workflow : definitionId;
    const nextRun = next.run !== undefined ? next.run : runId;
    if (nextTab === "runs") search.set("tab", "runs");
    if (workflow && nextTab === "workflows") search.set("workflow", workflow);
    if (nextRun) search.set("run", nextRun);
    const queryString = search.toString();
    router[mode](queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  }

  async function confirm() {
    if (!pending || confirming.current) return;
    confirming.current = true;
    try {
      if (pending.kind === "run-definition") {
        const result = await state.runDefinition(pending.definition.definition_id);
        if (result.run === null) { setPending({ ...pending, error: result.error }); return; }
        setPending(null);
        setNotice(`Started a run of ${pending.definition.name}.`);
        go({ tab: "workflows", workflow: pending.definition.definition_id, run: result.run.workflow_id });
      } else if (pending.kind === "delete") {
        const result = await state.remove(pending.run.workflow_id);
        if (!result.ok) { setPending({ ...pending, error: result.error }); return; }
        setPending(null);
        setNotice("Run deleted.");
        go({ run: null }, "replace");
      } else {
        const result = await state.lifecycle(pending.run.workflow_id, pending.kind);
        if (result.run === null) { setPending({ ...pending, error: result.error }); return; }
        setPending(null);
        setNotice(pending.kind === "start" ? "Run started." : "Run cancelled.");
      }
    } finally {
      confirming.current = false;
    }
  }

  async function quickAction(target: Workflow, action: "pause" | "resume") {
    const result = await state.lifecycle(target.workflow_id, action);
    setActionErrors((current) => ({ ...current, [target.workflow_id]: result.error ?? "" }));
    if (!result.error) setNotice(action === "pause" ? "Run paused." : "Run resumed.");
  }

  function request(target: Workflow, action: RunRequest) {
    if (action === "pause" || action === "resume") void quickAction(target, action);
    else setPending({ kind: action, run: target, error: null });
  }

  const definitions = filterDefinitions(state.definitions, query);
  const runs = filterRuns(state.runs, query, runFilter);
  const tabs: TabItem<Tab>[] = [
    { value: "workflows", label: "Workflows", badge: state.loaded ? state.definitions.length : undefined },
    { value: "runs", label: "Runs", badge: state.loaded ? state.runs.length : undefined },
  ];
  const pendingBusy = pending !== null && state.pendingIds.has(pending.kind === "run-definition" ? pending.definition.definition_id : pending.run.workflow_id);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8">
      <RealtimeNotifications events={realtime.latestEvent ? [realtime.latestEvent] : []} />
      <PageHeader
        title="Workflows"
        description="Multi-step jobs the server runs for you: each step calls a tool, in the order its dependencies allow. Runs keep going if you leave this page."
        actions={<Button variant="primary" icon={<Plus aria-hidden className="h-4 w-4" />} onClick={() => setBuilding(true)} disabled={tools === null}>Create workflow</Button>}
      />
      <p role="status" aria-live="polite" className={cn("text-sm text-success", !notice && "sr-only")}>{notice ?? ""}</p>

      {state.error && !state.loaded ? (
        <Alert tone="danger" action={<Button size="sm" onClick={() => void state.reload()} loading={state.loading}>Try again</Button>}>
          <p className="font-medium">Workflows couldn&apos;t be loaded.</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{state.error}</p>
        </Alert>
      ) : !state.loaded ? (
        <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading workflows">{Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-14 w-full" />)}</div>
      ) : state.definitions.length === 0 && state.runs.length === 0 ? (
        <EmptyState icon={WorkflowIcon} title="No workflows yet"
          description="Create one by listing the tool steps it should run and what each step waits for. Saving doesn't run anything; you start runs yourself."
          action={<Button variant="primary" size="sm" icon={<Plus aria-hidden className="h-3.5 w-3.5" />} onClick={() => setBuilding(true)} disabled={tools === null}>Create workflow</Button>} />
      ) : (
        <>
          {state.error && <Alert tone="warning" action={<Button size="sm" onClick={() => void state.reload()} loading={state.loading}>Refresh</Button>}>Couldn&apos;t refresh: {state.error}</Alert>}
          <div>
            <Tabs idPrefix={TAB_PREFIX} label="Workflow views" items={tabs} value={tab} onChange={(value) => go({ tab: value, workflow: null, run: null }, "replace")} />
            <div {...tabPanelProps(TAB_PREFIX, tab)} className="pt-5 focus:outline-none">
              <div className={cn("mb-4 flex flex-col gap-2 sm:flex-row sm:items-center", detailOpen && "hidden lg:flex")}>
                <div className="relative sm:w-72">
                  <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={tab === "runs" ? "Search runs" : "Search by name, step or tool"} aria-label={tab === "runs" ? "Search runs" : "Search workflows"} className="pl-8 pr-8" />
                  {query && <button type="button" onClick={() => setQuery("")} aria-label="Clear search" className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"><X aria-hidden className="h-3.5 w-3.5" /></button>}
                </div>
                {tab === "runs" && (
                  <Select aria-label="Run status" value={runFilter} onChange={(event) => setRunFilter(event.target.value as RunFilter)} className="sm:w-44">
                    {RUN_FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </Select>
                )}
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
                <div className={cn("min-w-0", detailOpen && "hidden lg:block")}>
                  {tab === "workflows" ? (
                    definitions.length === 0 ? (
                      <EmptyState icon={Search} title={state.definitions.length ? "No workflows match" : "No saved workflows"} description={state.definitions.length ? "Try another search." : "Runs exist, but their saved workflows aren't listed."}
                        action={query ? <Button size="sm" onClick={() => setQuery("")}>Clear search</Button> : undefined} />
                    ) : (
                      <ul aria-label="Saved workflows" className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
                        {definitions.map((item) => <DefinitionRow key={item.definition_id} definition={item} runs={runsOf(state.runs, item.definition_id)} tools={tools} now={now} selected={item.definition_id === definitionId} onSelect={() => go({ workflow: item.definition_id, run: null })} />)}
                      </ul>
                    )
                  ) : runs.length === 0 ? (
                    <EmptyState icon={Search} title={state.runs.length ? "No runs match" : "No runs yet"} description={state.runs.length ? "Try another search or status." : "Run a saved workflow to see it here."}
                      action={query || runFilter !== "all" ? <Button size="sm" onClick={() => { setQuery(""); setRunFilter("all"); }}>Clear filters</Button> : undefined} />
                  ) : (
                    <ul aria-label="Workflow runs" className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
                      {runs.map((item) => <RunRow key={item.workflow_id} run={item} now={now} selected={item.workflow_id === runId} onSelect={() => go({ run: item.workflow_id })} />)}
                    </ul>
                  )}
                </div>

                <section aria-label="Details" className={cn("min-w-0 rounded-lg border border-border bg-surface p-4 sm:p-5", !detailOpen && "hidden lg:block")}>
                  {run ? (
                    <RunView key={run.workflow_id} run={run} tools={toolMap} now={now} pending={state.pendingIds.has(run.workflow_id)} actionError={actionErrors[run.workflow_id] || null}
                      onRequest={(action) => request(run, action)}
                      onRetry={async (acknowledge) => { const result = await state.retry(run.workflow_id, acknowledge); if (!result.error) setNotice("Retry queued: unfinished steps will run again."); return result.error; }}
                      onBack={() => go({ run: null })}
                      onOpenDefinition={run.definition_id && state.definitions.some((item) => item.definition_id === run.definition_id) ? () => go({ tab: "workflows", workflow: run.definition_id, run: null }) : null} />
                  ) : tab === "workflows" && definition ? (
                    <DefinitionView key={definition.definition_id} definition={definition} runs={runsOf(state.runs, definition.definition_id)} tools={toolMap} now={now}
                      pending={state.pendingIds.has(definition.definition_id)} onRun={() => setPending({ kind: "run-definition", definition, error: null })}
                      onOpenRun={(id) => go({ run: id })} onBack={() => go({ workflow: null })} />
                  ) : (runId || definitionId) && state.loaded ? (
                    <EmptyState title="Not found" description="This workflow or run no longer exists. It may have been deleted." action={<Button size="sm" onClick={() => go({ workflow: null, run: null }, "replace")}>Back to the list</Button>} />
                  ) : (
                    <div className="flex min-h-48 flex-col items-center justify-center text-center">
                      <WorkflowIcon aria-hidden className="h-5 w-5 text-muted-foreground" />
                      <p className="mt-2 text-sm text-foreground">{tab === "runs" ? "Select a run to follow its steps" : "Select a workflow to see its steps"}</p>
                      <p className="mt-1 max-w-xs text-xs text-muted-foreground">Opening something never runs it.</p>
                    </div>
                  )}
                </section>
              </div>
            </div>
          </div>
        </>
      )}

      <CreateFromLink onCreate={() => setBuilding(true)} />
      {building && tools !== null && (
        <WorkflowBuilder tools={[...tools.values()]} onClose={() => setBuilding(false)}
          onCreate={async (input) => {
            const result = await state.create(input);
            if (result.run === null) return result.error;
            setNotice(`Saved ${result.run.name}. Its first run is ready; start it when you want.`);
            go({ tab: "workflows", workflow: result.run.definition_id, run: result.run.workflow_id });
            return null;
          }} />
      )}

      <ConfirmDialog pending={pending} busy={pendingBusy} tools={toolMap} onCancel={() => { if (!pendingBusy) setPending(null); }} onConfirm={() => void confirm()} />
    </div>
  );
}

function DefinitionRow({ definition, runs, tools, now, selected, onSelect }: { definition: StoredWorkflowDefinition; runs: Workflow[]; tools: ReadonlyMap<string, ToolDefinition> | null; now: Date; selected: boolean; onSelect: () => void }) {
  const latest = runs[0];
  const unavailable = tools && tools.size > 0 ? toolsUsed(definition.tasks).filter((name) => !tools.get(name)?.enabled) : [];
  return (
    <li>
      <button type="button" data-definition={definition.definition_id} onClick={onSelect} aria-current={selected ? "true" : undefined}
        className={cn("relative flex w-full flex-col gap-1 px-4 py-3 text-left transition-colors hover:bg-white/[0.025]", selected && "bg-white/[0.05]")}>
        {selected && <span aria-hidden className="absolute inset-y-2.5 left-0 w-0.5 rounded-full bg-accent" />}
        <span className="flex items-start justify-between gap-3">
          <span className="min-w-0 break-words text-sm font-medium text-foreground">{definition.name}</span>
          {latest ? <StatusBadge status={latest.status} className="shrink-0" /> : <span className="shrink-0 text-[11px] text-subtle">Not run yet</span>}
        </span>
        {definition.description && <span className="line-clamp-1 text-xs text-muted-foreground">{definition.description}</span>}
        <span className="text-[11px] text-subtle">
          {definition.tasks.length} step{definition.tasks.length === 1 ? "" : "s"} · v{definition.version}{latest ? ` · last run ${relativeTime(latest.created_at, now)}` : ""}
        </span>
        {unavailable.length > 0 && <span className="text-[11px] text-warning">Can&apos;t run: uses {unavailable.map(toolLabel).join(", ")}, which {unavailable.length === 1 ? "isn't" : "aren't"} available</span>}
      </button>
    </li>
  );
}

function RunRow({ run, now, selected, onSelect }: { run: Workflow; now: Date; selected: boolean; onSelect: () => void }) {
  const progress = runProgress(run);
  return (
    <li>
      <button type="button" data-run={run.workflow_id} onClick={onSelect} aria-current={selected ? "true" : undefined}
        className={cn("relative flex w-full flex-col gap-1 px-4 py-3 text-left transition-colors hover:bg-white/[0.025]", selected && "bg-white/[0.05]")}>
        {selected && <span aria-hidden className="absolute inset-y-2.5 left-0 w-0.5 rounded-full bg-accent" />}
        <span className="flex items-start justify-between gap-3">
          <span className="min-w-0 break-words text-sm text-foreground">{run.name}</span>
          <StatusBadge status={run.status} className="shrink-0" />
        </span>
        <span className="text-[11px] text-subtle">
          {progress.completed}/{progress.total} steps{run.definition_version ? ` · v${run.definition_version}` : ""}{run.attempt > 1 ? ` · attempt ${run.attempt}` : ""} · updated {relativeTime(run.updated_at, now)}
        </span>
      </button>
    </li>
  );
}

function ConfirmDialog({ pending, busy, tools, onCancel, onConfirm }: { pending: Pending | null; busy: boolean; tools: ReadonlyMap<string, ToolDefinition>; onCancel: () => void; onConfirm: () => void }) {
  const copy = !pending ? null
    : pending.kind === "run-definition" ? { title: `Run ${pending.definition.name}?`, body: `This creates a new run of version ${pending.definition.version} and the server starts it right away.`, steps: pending.definition.tasks, button: "Run workflow", danger: false }
    : pending.kind === "start" ? { title: "Start this run?", body: "The server starts its steps right away. Leaving this page won't stop it.", steps: pending.run.tasks, button: "Start run", danger: false }
    : pending.kind === "cancel" ? { title: "Cancel this run?", body: "Steps that haven't finished are cancelled, and a step that's running is stopped. A cancelled run can't be restarted.", steps: null, button: "Cancel run", danger: true }
    : { title: "Delete this run?", body: "This removes the run and its step history. The saved workflow isn't affected.", steps: null, button: "Delete run", danger: true };
  const external = copy?.steps ? toolsUsed(copy.steps).filter((name) => tools.get(name)?.side_effects) : [];

  return (
    <Dialog open={pending !== null} onClose={onCancel} title={copy?.title ?? ""} description={copy?.body}
      footer={pending && copy && (
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button onClick={onCancel} disabled={busy} data-autofocus>{pending.kind === "cancel" ? "Keep running" : "Cancel"}</Button>
          <Button variant={copy.danger ? "danger" : "primary"} onClick={onConfirm} loading={busy}>{copy.button}</Button>
        </div>
      )}>
      {pending && copy && (
        <div className="flex flex-col gap-3 text-sm">
          {copy.steps && (
            <p className="text-muted-foreground">
              {copy.steps.length} step{copy.steps.length === 1 ? "" : "s"} using {toolsUsed(copy.steps).map(toolLabel).join(", ")}. Each step calls its tool directly on the server; no Agent is involved.
            </p>
          )}
          {external.length > 0 && <Alert tone="warning"><span className="text-xs">{external.map(toolLabel).join(", ")} may change things outside Genesis.</span></Alert>}
          {pending.error && <Alert tone="danger">The server refused: {pending.error}</Alert>}
        </div>
      )}
    </Dialog>
  );
}
