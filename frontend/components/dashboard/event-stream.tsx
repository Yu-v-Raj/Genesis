"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, Bot, Cpu, Radio, Search, Workflow } from "lucide-react";

import type { RealtimeEvent } from "@/types/realtime";

type EventFilter = "all" | "agent" | "execution" | "runtime" | "system";
const filters: EventFilter[] = ["all", "agent", "execution", "runtime", "system"];

function category(event: RealtimeEvent): EventFilter {
  if (event.event_type.startsWith("agent.")) return "agent";
  if (event.event_type.startsWith("execution.")) return "execution";
  if (event.event_type.startsWith("system.") || event.event_type.startsWith("service.")) return "system";
  return "runtime";
}

function EventIcon({ event }: { event: RealtimeEvent }) {
  const type = category(event);
  const Icon = type === "agent" ? Bot : type === "execution" ? Workflow : type === "system" ? Cpu : Radio;
  return <Icon className="h-3.5 w-3.5" />;
}

/** Searchable, filtered event timeline backed by the bounded history and WebSocket updates. */
export function EventStream({ events }: { events: RealtimeEvent[] }) {
  const [filter, setFilter] = useState<EventFilter>("all");
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);
  const visibleEvents = useMemo(() => events.filter((event) => {
    const matchesFilter = filter === "all" || category(event) === filter;
    const haystack = `${event.event_type} ${event.source} ${JSON.stringify(event.payload)}`.toLowerCase();
    return matchesFilter && haystack.includes(query.trim().toLowerCase());
  }), [events, filter, query]);

  useEffect(() => {
    const container = containerRef.current;
    if (container !== null && autoScrollRef.current) container.scrollTop = container.scrollHeight;
  }, [visibleEvents]);

  return <section className="rounded-xl border border-border bg-surface shadow-sm">
    <div className="flex flex-col gap-3 border-b border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-semibold text-foreground">Live Event Stream</h2><p className="mt-1 text-xs text-muted-foreground">Newest first · live from the Genesis runtime</p></div><Activity className="h-4 w-4 text-primary" /></div>
      <div className="flex flex-col gap-2 sm:flex-row"><label className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-background px-3 py-2"><Search className="h-3.5 w-3.5 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search events" className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground" /></label><div className="flex flex-wrap gap-1">{filters.map((item) => <button key={item} type="button" onClick={() => setFilter(item)} className={`rounded-md px-2.5 py-1.5 text-xs font-medium capitalize transition-colors ${filter === item ? "bg-primary text-white" : "border border-border text-muted-foreground hover:bg-white/[0.05]"}`}>{item}</button>)}</div></div>
    </div>
    <div ref={containerRef} onScroll={(event) => { const { clientHeight, scrollHeight, scrollTop } = event.currentTarget; autoScrollRef.current = scrollHeight - scrollTop - clientHeight <= 32; }} className="max-h-96 overflow-y-auto divide-y divide-border">
      {visibleEvents.length === 0 ? <div className="flex flex-col items-center gap-2 px-6 py-12 text-center"><Radio className="h-7 w-7 text-primary/70" /><p className="text-sm font-medium text-foreground">No events found</p><p className="text-xs text-muted-foreground">Live runtime events will appear here automatically.</p></div> : visibleEvents.map((event) => <div key={event.id} className="flex gap-3 px-4 py-3 transition-colors hover:bg-white/[0.025]"><span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-primary/15 bg-primary/10 text-primary"><EventIcon event={event} /></span><div className="min-w-0 flex-1"><p className="text-xs font-medium text-foreground">{event.event_type.replaceAll(".", " ")}</p><p className="mt-1 truncate text-xs text-muted-foreground">{event.source} · {JSON.stringify(event.payload)}</p></div><time className="shrink-0 text-[11px] text-muted-foreground" title={new Date(event.timestamp).toLocaleString()}>{new Date(event.timestamp).toLocaleTimeString()}</time></div>)}</div>
  </section>;
}
