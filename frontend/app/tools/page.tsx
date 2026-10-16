"use client";

import { Suspense, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Calculator, Dices, Fingerprint, FlaskConical, MessageSquare, Search, ShieldAlert, Timer, Wrench, X, type LucideIcon } from "lucide-react";

import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { ToolDetail } from "@/components/tools/tool-detail";
import { ToolRunRow } from "@/components/tools/tool-run";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, tabPanelProps, type TabItem } from "@/components/ui/tabs";
import { useAgents } from "@/hooks/use-agents";
import { useNow } from "@/hooks/use-now";
import { useRealtime } from "@/hooks/use-realtime";
import { useTools } from "@/hooks/use-tools";
import { agentsAllowing, availableFilters, filterTools, toolLabel, type AvailabilityFilter, type EffectsFilter } from "@/lib/tools";
import { cn } from "@/lib/utils";
import type { ToolDefinition } from "@/types/tools";

const ICONS: Record<string, LucideIcon> = { calculator: Calculator, echo: MessageSquare, uuid: Fingerprint, random_number: Dices, delay: Timer, simulated_action: FlaskConical };
type Tab = "tools" | "runs";
const TAB_PREFIX = "tools";

export default function ToolsPage() {
  // The open tool and tab live in the URL (?tool=…&tab=runs); useSearchParams needs Suspense.
  return (
    <Suspense fallback={<div className="mx-auto max-w-6xl space-y-4 px-4 py-6 sm:px-6 sm:py-8" aria-busy="true"><Skeleton className="h-8 w-32" /><Skeleton className="h-80 w-full" /></div>}>
      <Tools />
    </Suspense>
  );
}

function Tools() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const realtime = useRealtime();
  const state = useTools(realtime);
  const { agents } = useAgents(realtime);
  const now = useNow();

  const [query, setQuery] = useState("");
  const [availability, setAvailability] = useState<AvailabilityFilter>("all");
  const [effects, setEffects] = useState<EffectsFilter>("all");
  const tab: Tab = params.get("tab") === "runs" ? "runs" : "tools";
  const selectedName = params.get("tool");
  const selected = state.tools.find((tool) => tool.name === selectedName) ?? null;
  const visible = filterTools(state.tools, { query, availability, effects });
  const showFilters = availableFilters(state.tools);
  const filtered = query.trim() !== "" || availability !== "all" || effects !== "all";

  function go(next: { tool?: string | null; tab?: Tab }, mode: "push" | "replace" = "replace") {
    const search = new URLSearchParams();
    const nextTab = next.tab ?? tab;
    const tool = next.tool !== undefined ? next.tool : selectedName;
    if (nextTab === "runs") search.set("tab", "runs");
    else if (tool) search.set("tool", tool);
    const queryString = search.toString();
    router[mode](queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  }

  function clearFilters() {
    setQuery("");
    setAvailability("all");
    setEffects("all");
  }

  const tabs: TabItem<Tab>[] = [
    { value: "tools", label: "Tools", badge: state.loading && state.tools.length === 0 ? undefined : state.tools.length },
    { value: "runs", label: "Recent runs", badge: state.loading && state.tasks.length === 0 ? undefined : state.tasks.length },
  ];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8">
      <RealtimeNotifications events={realtime.latestEvent ? [realtime.latestEvent] : []} />
      <PageHeader title="Tools" description="Capabilities Genesis can give your Agents. An Agent only uses the tools allowed in its settings, and the server checks every call." />

      {state.error && state.tools.length === 0 ? (
        <Alert tone="danger" action={<Button size="sm" onClick={() => void state.retry()} loading={state.loading}>Try again</Button>}>
          <p className="font-medium">Tools couldn&apos;t be loaded.</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{state.error}</p>
        </Alert>
      ) : (
        <>
          {state.error && <Alert tone="warning" action={<Button size="sm" onClick={() => void state.retry()} loading={state.loading}>Refresh</Button>}>Couldn&apos;t refresh: {state.error}</Alert>}
          <div>
            <Tabs idPrefix={TAB_PREFIX} label="Tools views" items={tabs} value={tab} onChange={(value) => go({ tab: value })} />
            <div {...tabPanelProps(TAB_PREFIX, tab)} className="pt-5 focus:outline-none">
              {tab === "runs" ? (
                <RecentRuns state={state} now={now} />
              ) : state.loading && state.tools.length === 0 ? (
                <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading tools">{Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-16 w-full" />)}</div>
              ) : state.tools.length === 0 ? (
                <EmptyState icon={Wrench} title="No tools registered" description="The server hasn't registered any tools, so Agents can only answer from the model." />
              ) : (
                <div className="flex flex-col gap-4">
                  <div className={cn("flex flex-col gap-2 sm:flex-row sm:items-center", selected && "hidden lg:flex")}>
                    <div className="relative sm:w-72">
                      <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <Input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tools" aria-label="Search tools by name, purpose or capability" className="pl-8 pr-8" />
                      {query && <button type="button" onClick={() => setQuery("")} aria-label="Clear search" className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"><X aria-hidden className="h-3.5 w-3.5" /></button>}
                    </div>
                    {showFilters.availability && (
                      <Select aria-label="Availability" value={availability} onChange={(event) => setAvailability(event.target.value as AvailabilityFilter)} className="sm:w-40">
                        <option value="all">Any availability</option><option value="enabled">Enabled</option><option value="disabled">Disabled</option>
                      </Select>
                    )}
                    {showFilters.effects && (
                      <Select aria-label="Effects" value={effects} onChange={(event) => setEffects(event.target.value as EffectsFilter)} className="sm:w-52">
                        <option value="all">Any effects</option><option value="none">No outside effects</option><option value="external">May change things outside</option>
                      </Select>
                    )}
                    <p className="text-xs text-muted-foreground sm:ml-auto" aria-live="polite">{filtered ? `${visible.length} of ${state.tools.length} tools` : `${state.tools.length} tools`}</p>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
                    <div className={cn("min-w-0", selected && "hidden lg:block")}>
                      {visible.length === 0 ? (
                        <EmptyState icon={Search} title="No tools match" description="Try another search or clear the filters." action={<Button size="sm" onClick={clearFilters}>Clear search and filters</Button>} />
                      ) : (
                        <ul aria-label="Tools" className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
                          {visible.map((tool) => <ToolRow key={tool.name} tool={tool} allowedCount={agentsAllowing(tool, agents).length} selected={tool.name === selectedName} onSelect={() => go({ tool: tool.name }, "push")} />)}
                        </ul>
                      )}
                    </div>
                    <section aria-label="Tool details" className={cn("min-w-0 rounded-lg border border-border bg-surface p-4 sm:p-5", !selected && "hidden lg:block")}>
                      {selected ? (
                        <ToolDetail key={selected.name} tool={selected} agents={agents} tasks={state.tasks} now={now}
                          pending={state.pendingToolNames.has(selected.name)} onRun={(args) => state.execute(selected.name, args)} onBack={() => go({ tool: null })} />
                      ) : (
                        <div className="flex min-h-48 flex-col items-center justify-center text-center">
                          <Wrench aria-hidden className="h-5 w-5 text-muted-foreground" />
                          <p className="mt-2 text-sm text-foreground">Select a tool to see what it does</p>
                          <p className="mt-1 max-w-xs text-xs text-muted-foreground">Its inputs, which Agents may use it, its restrictions and recent runs.</p>
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

function ToolRow({ tool, allowedCount, selected, onSelect }: { tool: ToolDefinition; allowedCount: number; selected: boolean; onSelect: () => void }) {
  const Icon = ICONS[tool.name] ?? Wrench;
  return (
    <li>
      <button type="button" data-tool={tool.name} onClick={onSelect} aria-current={selected ? "true" : undefined}
        className={cn("relative flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.025]", selected && "bg-white/[0.05]")}>
        {selected && <span aria-hidden className="absolute inset-y-2.5 left-0 w-0.5 rounded-full bg-accent" />}
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border-strong bg-surface-2 text-muted-foreground"><Icon aria-hidden className="h-4 w-4" /></span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-foreground">{toolLabel(tool.name)}</span>
            {!tool.enabled && <StatusBadge status="disabled" />}
          </span>
          <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{tool.description}</span>
          <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-subtle">
            <span>{allowedCount === 0 ? "Not allowed for any Agent" : `Allowed for ${allowedCount} Agent${allowedCount === 1 ? "" : "s"}`}</span>
            {tool.side_effects && <span className="inline-flex items-center gap-1 text-warning"><ShieldAlert aria-hidden className="h-3 w-3" />May change things outside Genesis</span>}
          </span>
        </span>
      </button>
    </li>
  );
}

function RecentRuns({ state, now }: { state: ReturnType<typeof useTools>; now: Date }) {
  if (state.loading && state.tasks.length === 0) return <div className="flex flex-col gap-2" aria-busy="true">{Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-10 w-full" />)}</div>;
  if (state.tasks.length === 0) return <EmptyState icon={Wrench} title="No tool runs yet" description="Runs appear here when an Agent calls a tool, a workflow step runs, or you run a test. They're stored, so they stay after a restart." />;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">Newest first, from stored history. Expand a run to see its arguments (secret-looking values hidden) and result.</p>
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <ul aria-label="Recent tool runs" className="divide-y divide-border">
          {state.tasks.map((task) => <ToolRunRow key={task.task_id} task={task} now={now} showTool />)}
        </ul>
        {state.hasOlder ? (
          <button type="button" onClick={() => void state.loadOlder()} disabled={state.loadingOlder} className="w-full border-t border-border py-2 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-60">
            {state.loadingOlder ? "Loading…" : "Load older runs"}
          </button>
        ) : (
          <p className="border-t border-border py-2 text-center text-[11px] text-subtle">That&apos;s every stored run.</p>
        )}
      </div>
    </div>
  );
}
