"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BrainCircuit, ChevronDown, Plus, Search, X } from "lucide-react";

import { AgentAvatar } from "@/components/agents/agent-avatar";
import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { MemoryEditor } from "@/components/memory/memory-editor";
import { MemoryDetail, MemoryRow } from "@/components/memory/memory-record";
import { Button, buttonClasses } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { Input } from "@/components/ui/field";
import { Menu } from "@/components/ui/menu";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { useAgents } from "@/hooks/use-agents";
import { useMemory } from "@/hooks/use-memory";
import { useNow } from "@/hooks/use-now";
import { useRealtime } from "@/hooks/use-realtime";
import { filterByKind, kindFilters, summarize, type KindFilter } from "@/lib/memory";
import { statusPresentation } from "@/lib/status";
import { cn } from "@/lib/utils";
import type { Agent } from "@/types/agents";
import type { CreateMemoryInput, MemoryRecord } from "@/types/memory";

const SEARCH_DELAY_MS = 300;

export default function MemoryPage() {
  // The Agent and the open memory live in the URL (?agent=…&memory=…) so a reload, the
  // Back button or a link from an Agent opens the same place. useSearchParams needs Suspense.
  return (
    <Suspense fallback={<MemorySkeleton />}>
      <MemoryLibrary />
    </Suspense>
  );
}

function MemorySkeleton() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8" aria-busy="true">
      <Skeleton className="h-8 w-40" /><Skeleton className="h-14 w-full" /><Skeleton className="h-80 w-full" />
    </div>
  );
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

type Editing = { mode: "add" } | { mode: "edit"; record: MemoryRecord } | null;

function MemoryLibrary() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const realtime = useRealtime();
  const agentsState = useAgents(realtime);
  const now = useNow();

  const agents = agentsState.agents;
  const requestedAgentId = params.get("agent");
  // The requested Agent while it exists, otherwise the first one (as before).
  const agent: Agent | null = agents.find((item) => item.id === requestedAgentId) ?? agents[0] ?? null;
  const selectedMemoryId = params.get("memory");

  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounced(query, SEARCH_DELAY_MS);
  const [kind, setKind] = useState<KindFilter>("all");
  const [editing, setEditing] = useState<Editing>(null);
  const [deleting, setDeleting] = useState<{ record: MemoryRecord; error: string | null } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const memory = useMemory(agent?.id ?? null, debouncedQuery, realtime);
  // Only records that answer this Agent and this search; never another Agent's.
  const current = memory.view && agent && memory.view.agentId === agent.id && memory.view.query === debouncedQuery.trim()
    ? memory.records.filter((record) => record.agent_id === agent.id)
    : null;
  const filters = current ? kindFilters(current) : [];
  const activeKind = filters.some((item) => item.value === kind) ? kind : "all";
  const visible = current ? filterByKind(current, activeKind) : [];
  const selected = current?.find((record) => record.memory_id === selectedMemoryId) ?? null;
  const searching = query.trim() !== "";
  const settling = query.trim() !== debouncedQuery.trim() || (memory.loading && current !== null);

  useEffect(() => {
    if (notice === null) return;
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  function navigate(next: { agent?: string | null; memory?: string | null }, mode: "push" | "replace" = "replace") {
    const search = new URLSearchParams();
    const agentId = next.agent !== undefined ? next.agent : agent?.id ?? null;
    const memoryId = next.memory !== undefined ? next.memory : selectedMemoryId;
    if (agentId) search.set("agent", agentId);
    if (memoryId) search.set("memory", memoryId);
    const queryString = search.toString();
    router[mode](queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  }

  function switchAgent(agentId: string) {
    setQuery("");
    setKind("all");
    navigate({ agent: agentId, memory: null }, "push");
  }

  async function submitEditor(input: CreateMemoryInput): Promise<string | null> {
    if (!agent || !editing) return "No Agent is selected.";
    if (editing.mode === "add") {
      const result = await memory.create(agent.id, input);
      if (result.record === null) return result.error;
      setNotice(`Memory added to ${agent.name}.`);
      setQuery("");
      setKind("all");
      navigate({ memory: result.record.memory_id });
      return null;
    }
    const result = await memory.update(editing.record.memory_id, input);
    if (result.record === null) return result.error;
    setNotice("Changes saved.");
    return null;
  }

  async function confirmDelete() {
    if (!deleting) return;
    const result = await memory.remove(deleting.record.memory_id);
    if (!result.ok) {
      setDeleting({ ...deleting, error: result.error });
      return;
    }
    setDeleting(null);
    setNotice("Memory deleted.");
    if (selectedMemoryId === deleting.record.memory_id) navigate({ memory: null });
  }

  const agentMenu = agents.map((item) => ({
    key: item.id,
    label: item.name,
    description: statusPresentation(item.status).label,
    checked: item.id === agent?.id,
    onSelect: () => switchAgent(item.id),
  }));

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8">
      <RealtimeNotifications events={realtime.latestEvent ? [realtime.latestEvent] : []} />
      <PageHeader
        title="Memory"
        description="What each Agent remembers. Memories are included with every message the Agent receives — review, edit or remove them here."
        actions={agent && <Button variant="primary" icon={<Plus aria-hidden className="h-4 w-4" />} onClick={() => setEditing({ mode: "add" })}>Add memory</Button>}
      />
      <p role="status" aria-live="polite" className={cn("text-sm text-success", !notice && "sr-only")}>{notice ?? ""}</p>

      {agentsState.loading && agents.length === 0 ? (
        <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading Agents"><Skeleton className="h-14 w-full" /><Skeleton className="h-64 w-full" /></div>
      ) : agentsState.error && agents.length === 0 ? (
        <Alert tone="danger" action={<Button size="sm" onClick={() => void agentsState.retry()}>Try again</Button>}>
          <p className="font-medium">Agents couldn&apos;t be loaded, so their memories can&apos;t be shown.</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{agentsState.error}</p>
        </Alert>
      ) : agent === null ? (
        <EmptyState icon={BrainCircuit} title="No Agents yet" description="Memories belong to an Agent. Create an Agent first, then add what it should remember."
          action={<Link href="/agents?create=1" className={buttonClasses("primary", "sm")}><Plus aria-hidden className="h-3.5 w-3.5" />Create an Agent</Link>} />
      ) : (
        <>
          <section aria-label="Agent" className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4">
            <div className="flex min-w-0 items-center gap-3">
              <AgentAvatar name={agent.name} />
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wider text-subtle">Memories of</p>
                <p className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-sm font-semibold text-foreground" title={agent.name}>{agent.name}</span>
                  <StatusBadge status={agent.status} className="shrink-0" />
                </p>
              </div>
            </div>
            <Menu heading="Show memories of" triggerLabel={`Change Agent (current: ${agent.name})`} items={agentMenu} width="w-72" align="end"
              trigger={<>Change Agent<ChevronDown aria-hidden className="h-3.5 w-3.5" /></>} triggerClassName={cn(buttonClasses("secondary", "sm"), "self-start sm:self-auto")} />
          </section>

          <div className={cn("flex flex-col gap-2", selected && "hidden lg:flex")}>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="relative sm:w-80">
                <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input ref={searchRef} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search text, tags and metadata"
                  aria-label={`Search ${agent.name}'s memories`} aria-describedby="memory-search-hint" className="pl-8 pr-8" />
                {query && (
                  <button type="button" onClick={() => { setQuery(""); searchRef.current?.focus(); }} aria-label="Clear search" className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground">
                    <X aria-hidden className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
              {filters.length > 2 && (
                <div role="group" aria-label="Filter by kind" className="flex flex-wrap gap-1">
                  {filters.map((item) => (
                    <button key={item.value} type="button" aria-pressed={activeKind === item.value} onClick={() => setKind(item.value)}
                      className={cn("inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors", activeKind === item.value ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground")}>
                      {item.label}<span className="tabular-nums text-subtle">{item.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <p id="memory-search-hint" className="text-[11px] text-subtle" aria-live="polite">
              {current === null ? (memory.error ? "" : "Loading…")
                : searching ? `${current.length} ${current.length === 1 ? "memory matches" : "memories match"} “${debouncedQuery.trim()}” (plain text match, not case-sensitive)${settling ? " · updating…" : ""}`
                : `${current.length} ${current.length === 1 ? "memory" : "memories"}${activeKind !== "all" ? ` · showing ${visible.length}` : ""}${settling ? " · updating…" : ""}`}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
            <div className={cn("min-w-0", selected && "hidden lg:block")}>
              {memory.error && current === null ? (
                <Alert tone="danger" action={<Button size="sm" onClick={memory.reload}>Try again</Button>}>
                  <p className="font-medium">{searching ? "The search failed." : `${agent.name}'s memories couldn't be loaded.`}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{memory.error}</p>
                </Alert>
              ) : current === null ? (
                <div className="flex flex-col gap-px overflow-hidden rounded-lg border border-border bg-border" aria-busy="true" aria-label="Loading memories">
                  {Array.from({ length: 3 }, (_, index) => <div key={index} className="space-y-2 bg-surface p-4"><Skeleton className="h-4 w-11/12" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-3 w-24" /></div>)}
                </div>
              ) : current.length === 0 ? (
                searching ? (
                  <EmptyState icon={Search} title="No memories match" description={`Nothing in ${agent.name}'s memory contains “${debouncedQuery.trim()}”.`}
                    action={<Button size="sm" onClick={() => { setQuery(""); searchRef.current?.focus(); }}>Clear search</Button>} />
                ) : (
                  <EmptyState icon={BrainCircuit} title={`${agent.name} doesn't remember anything yet`}
                    description="Add facts, preferences or context this Agent should know. They'll be included with every message it receives."
                    action={<Button variant="primary" size="sm" icon={<Plus aria-hidden className="h-3.5 w-3.5" />} onClick={() => setEditing({ mode: "add" })}>Add memory</Button>} />
                )
              ) : (
                <div className="overflow-hidden rounded-lg border border-border bg-surface">
                  {memory.error && <Alert tone="warning" className="m-2"><span className="text-xs">Couldn&apos;t refresh: {memory.error}</span></Alert>}
                  <ul aria-label={`${agent.name}'s memories`} className={cn("max-h-[38rem] divide-y divide-border overflow-y-auto transition-opacity", settling && "opacity-70")}>
                    {visible.map((record) => (
                      <MemoryRow key={record.memory_id} record={record} selected={record.memory_id === selectedMemoryId} now={now}
                        onSelect={() => navigate({ memory: record.memory_id }, "push")} />
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <section aria-label="Memory details" className={cn("min-w-0 rounded-lg border border-border bg-surface p-4 sm:p-5", !selected && "hidden lg:block")}>
              {selected ? (
                <MemoryDetail key={selected.memory_id} record={selected} agentName={agent.name} now={now} busy={memory.pendingIds.has(selected.memory_id)}
                  onEdit={() => setEditing({ mode: "edit", record: selected })}
                  onDelete={() => setDeleting({ record: selected, error: null })}
                  onBack={() => navigate({ memory: null })} />
              ) : (
                <div className="flex min-h-48 flex-col items-center justify-center text-center">
                  <BrainCircuit aria-hidden className="h-5 w-5 text-muted-foreground" />
                  <p className="mt-2 text-sm text-foreground">Select a memory to read it in full</p>
                  <p className="mt-1 max-w-xs text-xs text-muted-foreground">You can edit or delete it from there.</p>
                </div>
              )}
            </section>
          </div>
        </>
      )}

      {editing && agent && (
        <MemoryEditor key={editing.mode === "edit" ? editing.record.memory_id : "new"} record={editing.mode === "edit" ? editing.record : null}
          agentName={agent.name} onClose={() => setEditing(null)} onSubmit={submitEditor} />
      )}

      <Dialog
        open={deleting !== null}
        onClose={() => { if (!deleting || !memory.pendingIds.has(deleting.record.memory_id)) setDeleting(null); }}
        title="Delete this memory?"
        description={agent ? `${agent.name} will no longer remember it. This can't be undone.` : undefined}
        footer={deleting && (
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button onClick={() => setDeleting(null)} disabled={memory.pendingIds.has(deleting.record.memory_id)} data-autofocus>Cancel</Button>
            <Button variant="danger" onClick={() => void confirmDelete()} loading={memory.pendingIds.has(deleting.record.memory_id)}>Delete memory</Button>
          </div>
        )}
      >
        {deleting && (
          <div className="flex flex-col gap-3">
            <blockquote className="break-words rounded-md border border-border bg-surface-2 px-3 py-2 text-sm leading-6 text-foreground">“{summarize(deleting.record.content, 240)}”</blockquote>
            {deleting.error && <Alert tone="danger">It wasn&apos;t deleted: {deleting.error}</Alert>}
          </div>
        )}
      </Dialog>
    </div>
  );
}
