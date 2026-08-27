"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  FileText,
  Info,
  LoaderCircle,
  Pencil,
  Plus,
  Search,
  Tag,
  Trash2,
  X,
} from "lucide-react";

import { ErrorState } from "@/components/dashboard/error-state";
import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { RealtimeStatus } from "@/components/dashboard/realtime-status";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { useAgents } from "@/hooks/use-agents";
import { useMemory } from "@/hooks/use-memory";
import { useRealtime } from "@/hooks/use-realtime";
import { cn } from "@/lib/utils";
import type { CreateMemoryInput, MemoryKind, MemoryRecord } from "@/types/memory";

const kinds: MemoryKind[] = ["fact", "note", "preference", "context"];
const kindTone: Record<MemoryKind, string> = {
  fact: "border-sky-400/25 bg-sky-400/10 text-sky-200",
  note: "border-violet-400/25 bg-violet-400/10 text-violet-200",
  preference: "border-pink-400/25 bg-pink-400/10 text-pink-200",
  context: "border-amber-400/25 bg-amber-400/10 text-amber-200",
};

function formattedTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function parseTags(value: string): string[] {
  return [...new Set(value.split(",").map((tag) => tag.trim()).filter(Boolean))];
}

function metadataText(metadata: Record<string, unknown>): string {
  return Object.keys(metadata).length === 0 ? "" : JSON.stringify(metadata, null, 2);
}

function parseMetadata(value: string): Record<string, unknown> | null {
  if (!value.trim()) return {};
  try {
    const parsed: unknown = JSON.parse(value);
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}

function KindBadge({ kind }: { kind: MemoryKind }) {
  return <span className={cn("inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize", kindTone[kind])}>{kind}</span>;
}

function MemoryForm({ initial, pending, submitLabel, onCancel, onSubmit }: {
  initial?: MemoryRecord;
  pending: boolean;
  submitLabel: string;
  onCancel?: () => void;
  onSubmit: (input: CreateMemoryInput) => Promise<boolean>;
}) {
  const [content, setContent] = useState(initial?.content ?? "");
  const [kind, setKind] = useState<MemoryKind>(initial?.kind ?? "note");
  const [tags, setTags] = useState(initial?.tags.join(", ") ?? "");
  const [metadata, setMetadata] = useState(metadataText(initial?.metadata ?? {}));
  const [validation, setValidation] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedMetadata = parseMetadata(metadata);
    if (!content.trim()) return setValidation("Content is required.");
    if (content.trim().length > 10_000) return setValidation("Content must be 10,000 characters or fewer.");
    if (parsedMetadata === null) return setValidation("Metadata must be a JSON object.");
    setValidation(null);
    const saved = await onSubmit({ content: content.trim(), kind, tags: parseTags(tags), metadata: parsedMetadata });
    if (saved && !initial) {
      setContent("");
      setKind("note");
      setTags("");
      setMetadata("");
    }
  }

  return <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate>
    <label className="block text-sm font-medium text-foreground">Content<textarea value={content} onChange={(event) => setContent(event.target.value)} required maxLength={10_000} rows={5} className="mt-1.5 w-full resize-y rounded-lg border border-border bg-background/60 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/25" placeholder="What should this agent remember?" /></label>
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="block text-sm font-medium text-foreground">Kind<select value={kind} onChange={(event) => setKind(event.target.value as MemoryKind)} className="mt-1.5 w-full rounded-lg border border-border bg-background/60 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/25">{kinds.map((value) => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></label>
      <label className="block text-sm font-medium text-foreground">Tags<span className="ml-1 font-normal text-muted-foreground">(comma separated)</span><input value={tags} onChange={(event) => setTags(event.target.value)} className="mt-1.5 w-full rounded-lg border border-border bg-background/60 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/25" placeholder="project, runtime" /></label>
    </div>
    <label className="block text-sm font-medium text-foreground">Metadata <span className="font-normal text-muted-foreground">(JSON object)</span><textarea value={metadata} onChange={(event) => setMetadata(event.target.value)} rows={3} className="mt-1.5 w-full resize-y rounded-lg border border-border bg-background/60 px-3 py-2 font-mono text-xs text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/25" placeholder={'{"source":"operator"}'} /></label>
    {validation && <p role="alert" className="flex items-center gap-2 rounded-lg border border-red-400/25 bg-red-400/5 px-3 py-2 text-sm text-red-200"><CircleAlert className="h-4 w-4 shrink-0" />{validation}</p>}
    <div className="flex flex-wrap justify-end gap-2"><>{onCancel && <button type="button" onClick={onCancel} disabled={pending} className="rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition hover:bg-white/5 hover:text-foreground disabled:opacity-50">Cancel</button>}</><button type="submit" disabled={pending} className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white transition hover:bg-primary/85 disabled:cursor-not-allowed disabled:opacity-50">{pending && <LoaderCircle className="h-4 w-4 animate-spin" />}{pending ? "Saving…" : submitLabel}</button></div>
  </form>;
}

export default function MemoryPage() {
  const realtime = useRealtime();
  const agentsState = useAgents(realtime);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const memory = useMemory(selectedAgentId, realtime);
  const [selected, setSelected] = useState<MemoryRecord | null>(null);
  const [search, setSearch] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [creating, setCreating] = useState(false);
  const notificationEvents = useMemo(
    () => realtime.latestEvent ? [realtime.latestEvent] : [],
    [realtime.latestEvent]
  );

  useEffect(() => {
    if (selectedAgentId !== null && !agentsState.agents.some((agent) => agent.id === selectedAgentId)) setSelectedAgentId(null);
    if (selectedAgentId === null && agentsState.agents.length > 0) setSelectedAgentId(agentsState.agents[0].id);
  }, [agentsState.agents, selectedAgentId]);

  useEffect(() => {
    if (selected && !memory.memories.some((item) => item.memory_id === selected.memory_id)) {
      setSelected(null);
      setEditing(false);
      setConfirmDelete(false);
    } else if (selected) {
      setSelected(memory.memories.find((item) => item.memory_id === selected.memory_id) ?? null);
    }
  }, [memory.memories, selected]);

  const counts = useMemo(() => kinds.map((kind) => ({ kind, count: memory.memories.filter((item) => item.kind === kind).length })), [memory.memories]);
  const selectedAgent = agentsState.agents.find((agent) => agent.id === selectedAgentId);

  async function runSearch(event?: FormEvent) {
    event?.preventDefault();
    if (selectedAgentId === null) return;
    if (!search.trim()) return memory.load(selectedAgentId);
    await memory.search(selectedAgentId, search.trim());
  }

  async function create(input: CreateMemoryInput): Promise<boolean> {
    if (selectedAgentId === null) return false;
    setCreating(true);
    try {
      const record = await memory.create(selectedAgentId, input);
      if (record) {
        setSelected(record);
        setAddOpen(false);
        return true;
      }
      return false;
    } finally { setCreating(false); }
  }

  async function update(input: CreateMemoryInput): Promise<boolean> {
    if (!selected) return false;
    const record = await memory.update(selected.memory_id, input);
    if (record) { setSelected(record); setEditing(false); return true; }
    return false;
  }

  async function remove() {
    if (!selected) return;
    if (await memory.remove(selected.memory_id)) { setSelected(null); setConfirmDelete(false); }
  }

  const retry = () => selectedAgentId && void memory.load(selectedAgentId);

  return <div className="flex h-screen w-full overflow-hidden"><Sidebar /><div className="flex min-w-0 flex-1 flex-col overflow-hidden"><Topbar /><main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8"><div className="mx-auto flex max-w-7xl flex-col gap-6"><RealtimeNotifications events={notificationEvents} />
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><div><div className="flex items-center gap-2"><BrainCircuit className="h-5 w-5 text-primary" /><h1 className="text-2xl font-semibold tracking-tight text-foreground">Memory</h1></div><p className="mt-1 text-sm text-muted-foreground">Genesis agents store and retrieve runtime knowledge here.</p><div className="mt-2"><RealtimeStatus connectionStatus={realtime.connectionStatus} runtimeState="memory runtime" lastHeartbeat={null} /></div></div><button type="button" onClick={() => setAddOpen(true)} disabled={!selectedAgentId} className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white shadow-sm shadow-primary/20 transition hover:bg-primary/85 disabled:cursor-not-allowed disabled:opacity-50"><Plus className="h-4 w-4" />Add Memory</button></div>
    {agentsState.loading ? <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted-foreground"><LoaderCircle className="mr-2 inline h-4 w-4 animate-spin" />Loading agents…</div> : agentsState.error && agentsState.agents.length === 0 ? <ErrorState message={agentsState.error} onRetry={() => void agentsState.retry()} /> : agentsState.agents.length === 0 ? <section className="rounded-xl border border-dashed border-border bg-surface px-6 py-14 text-center"><BrainCircuit className="mx-auto h-8 w-8 text-primary" /><h2 className="mt-4 text-lg font-semibold text-foreground">No agents available</h2><p className="mt-2 text-sm text-muted-foreground">Create an agent before adding agent-scoped runtime memory.</p></section> : <>
      <section className="grid gap-4 rounded-xl border border-border bg-surface p-4 shadow-sm lg:grid-cols-[minmax(0,1fr)_auto]"><label className="min-w-0 text-sm font-medium text-foreground">Agent<select aria-label="Select an agent" value={selectedAgentId ?? ""} onChange={(event) => { setSelectedAgentId(event.target.value || null); setSearch(""); setSelected(null); }} className="mt-1.5 w-full rounded-lg border border-border bg-background/60 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/25">{agentsState.agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label><div className="self-end text-xs text-muted-foreground">{selectedAgent?.description || "Agent-scoped memory"}</div></section>
      <section aria-label="Memory statistics" className="grid grid-cols-2 gap-3 sm:grid-cols-5"><div className="rounded-xl border border-border bg-surface px-4 py-3 shadow-sm"><span className="text-xs font-medium text-muted-foreground">Memory count</span><p className="mt-2 text-2xl font-semibold text-foreground">{memory.memories.length}</p></div>{counts.map(({ kind, count }) => <div key={kind} className="rounded-xl border border-border bg-surface px-4 py-3 shadow-sm"><KindBadge kind={kind} /><p className="mt-2 text-2xl font-semibold text-foreground">{count}</p></div>)}</section>
      {memory.error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-400/25 bg-red-400/5 px-4 py-3 text-sm text-red-200"><span>{memory.error}</span><button type="button" onClick={retry} className="rounded-md border border-red-400/25 px-3 py-1.5 text-xs font-medium transition hover:bg-red-400/10">Retry</button></div>}
      <form onSubmit={(event) => void runSearch(event)} className="flex flex-col gap-2 sm:flex-row"><label className="relative min-w-0 flex-1"><span className="sr-only">Search memories</span><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><input value={search} onChange={(event) => setSearch(event.target.value)} className="w-full rounded-lg border border-border bg-surface py-2 pl-9 pr-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/25" placeholder="Search this agent's memories" /></label><button type="submit" disabled={memory.searching} className="inline-flex items-center justify-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground transition hover:bg-white/5 hover:text-foreground disabled:opacity-50">{memory.searching && <LoaderCircle className="h-4 w-4 animate-spin" />}Search</button>{search && <button type="button" onClick={() => { setSearch(""); retry(); }} className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition hover:bg-white/5 hover:text-foreground"><X className="h-4 w-4" />Clear</button>}</form>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(340px,0.8fr)]"><section className="min-w-0 space-y-3">{memory.loading ? <div className="rounded-xl border border-border bg-surface p-8 text-center text-sm text-muted-foreground"><LoaderCircle className="mx-auto mb-3 h-5 w-5 animate-spin text-primary" />Loading memories…</div> : memory.memories.length === 0 ? <div className="rounded-xl border border-dashed border-border bg-surface p-10 text-center"><FileText className="mx-auto h-7 w-7 text-primary" /><h2 className="mt-3 font-semibold text-foreground">{search ? "No matching memories" : "No memories yet"}</h2><p className="mt-1 text-sm text-muted-foreground">{search ? "Try a different deterministic text search." : "Add runtime knowledge for this agent."}</p></div> : memory.memories.map((item) => <button key={item.memory_id} type="button" onClick={() => { setSelected(item); setEditing(false); setConfirmDelete(false); }} className={cn("w-full rounded-xl border bg-surface p-4 text-left shadow-sm transition hover:border-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary", selected?.memory_id === item.memory_id ? "border-primary/60 ring-1 ring-primary/25" : "border-border")}><div className="flex items-start gap-3"><FileText className="mt-0.5 h-4 w-4 shrink-0 text-primary" /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><KindBadge kind={item.kind} /><span className="text-xs text-muted-foreground">Updated {formattedTime(item.updated_at)}</span></div><p className="mt-2 line-clamp-2 text-sm leading-6 text-foreground">{item.content}</p>{item.tags.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{item.tags.map((tag) => <span key={tag} className="inline-flex items-center gap-1 rounded-md border border-white/[0.08] bg-white/[0.04] px-1.5 py-0.5 text-[11px] text-muted-foreground"><Tag className="h-3 w-3" />{tag}</span>)}</div>}</div><ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" /></div></button>)}</section>
      <aside className="min-w-0"><section className="sticky top-2 rounded-xl border border-border bg-surface p-5 shadow-sm">{!selected ? <div className="py-10 text-center"><Info className="mx-auto h-6 w-6 text-primary" /><h2 className="mt-3 font-semibold text-foreground">Select a memory</h2><p className="mt-1 text-sm text-muted-foreground">View and manage its full runtime record.</p></div> : editing ? <><div className="mb-5 flex items-center justify-between"><h2 className="font-semibold text-foreground">Edit memory</h2><KindBadge kind={selected.kind} /></div><MemoryForm initial={selected} pending={memory.pendingMemoryIds.has(selected.memory_id)} submitLabel="Save changes" onCancel={() => setEditing(false)} onSubmit={update} /></> : <><div className="flex items-start justify-between gap-3"><div><div className="flex items-center gap-2"><h2 className="font-semibold text-foreground">Memory details</h2><KindBadge kind={selected.kind} /></div><p className="mt-1 break-all font-mono text-[11px] text-muted-foreground">{selected.memory_id}</p></div><div className="flex gap-1"><button type="button" onClick={() => setEditing(true)} aria-label="Edit memory" className="rounded-md p-2 text-muted-foreground transition hover:bg-white/5 hover:text-foreground"><Pencil className="h-4 w-4" /></button><button type="button" onClick={() => setConfirmDelete(true)} aria-label="Delete memory" className="rounded-md p-2 text-red-300 transition hover:bg-red-400/10"><Trash2 className="h-4 w-4" /></button></div></div><p className="mt-5 whitespace-pre-wrap text-sm leading-6 text-foreground">{selected.content}</p><dl className="mt-5 space-y-3 border-t border-border pt-4 text-xs"><div><dt className="text-muted-foreground">Agent ID</dt><dd className="mt-1 break-all font-mono text-foreground">{selected.agent_id}</dd></div><div><dt className="text-muted-foreground">Created</dt><dd className="mt-1 text-foreground">{formattedTime(selected.created_at)}</dd></div><div><dt className="text-muted-foreground">Updated</dt><dd className="mt-1 text-foreground">{formattedTime(selected.updated_at)}</dd></div>{selected.tags.length > 0 && <div><dt className="text-muted-foreground">Tags</dt><dd className="mt-1 flex flex-wrap gap-1.5">{selected.tags.map((tag) => <span key={tag} className="rounded-md border border-white/[0.08] bg-white/[0.04] px-1.5 py-0.5 text-muted-foreground">{tag}</span>)}</dd></div>}<div><dt className="text-muted-foreground">Metadata</dt><dd className="mt-1"><pre className="max-h-48 overflow-auto rounded-lg border border-white/[0.07] bg-background/70 p-3 font-mono text-[11px] leading-5 text-slate-200">{metadataText(selected.metadata) || "{}"}</pre></dd></div></dl>{confirmDelete && <div role="alertdialog" aria-label="Confirm memory deletion" className="mt-5 rounded-lg border border-red-400/25 bg-red-400/5 p-3"><p className="text-sm text-red-100">Delete this memory? This cannot be undone.</p><div className="mt-3 flex justify-end gap-2"><button type="button" onClick={() => setConfirmDelete(false)} className="rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-white/5">Cancel</button><button type="button" onClick={() => void remove()} disabled={memory.pendingMemoryIds.has(selected.memory_id)} className="inline-flex items-center gap-1.5 rounded-md bg-red-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-400 disabled:opacity-50">{memory.pendingMemoryIds.has(selected.memory_id) && <LoaderCircle className="h-3.5 w-3.5 animate-spin" />}Delete</button></div></div>}</>}</section></aside></div>
    </>}</div></main></div>{addOpen && <div role="dialog" aria-modal="true" aria-labelledby="add-memory-title" className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"><div className="max-h-[calc(100vh-2rem)] w-full max-w-2xl overflow-y-auto rounded-xl border border-border bg-surface p-5 shadow-2xl"><div className="mb-5 flex items-center justify-between"><div><h2 id="add-memory-title" className="font-semibold text-foreground">Add Memory</h2><p className="mt-1 text-xs text-muted-foreground">{selectedAgent?.name}</p></div><button type="button" onClick={() => setAddOpen(false)} aria-label="Close add memory dialog" className="rounded-md p-2 text-muted-foreground hover:bg-white/5 hover:text-foreground"><X className="h-4 w-4" /></button></div><MemoryForm pending={creating} submitLabel="Add memory" onCancel={() => setAddOpen(false)} onSubmit={create} /></div></div>}</div>;
}
