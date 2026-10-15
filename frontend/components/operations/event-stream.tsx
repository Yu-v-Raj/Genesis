"use client";

import { useMemo, useState } from "react";
import { Activity, Bot, Brain, ChevronRight, Cpu, Database, Radio, Search, Workflow, Wrench, type LucideIcon } from "lucide-react";

import { CopyButton } from "@/components/ui/copy-button";
import { JsonView } from "@/components/ui/disclosure";
import { EmptyState } from "@/components/ui/feedback";
import { Input } from "@/components/ui/field";
import { EVENT_CATEGORIES, describeEvent, eventCategory, isRoutineEvent, type EventCategory } from "@/lib/activity";
import { relativeTime } from "@/lib/operations";
import { cn } from "@/lib/utils";
import type { RealtimeEvent } from "@/types/realtime";

const ICONS: Record<EventCategory, LucideIcon> = {
  agent: Bot, execution: Activity, model: Brain, tool: Wrench, memory: Database, workflow: Workflow, system: Cpu, log: Radio,
};

const PAGE = 100;

function EventRow({ event, agentNames, now }: { event: RealtimeEvent; agentNames: Record<string, string>; now: Date }) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[eventCategory(event.event_type)];
  return (
    <li>
      <button type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)} className="flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-white/[0.025]">
        <Icon aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1">
          <span className="block break-words text-xs text-foreground">{describeEvent(event, agentNames)}</span>
          <span className="mt-0.5 block font-mono text-[11px] text-muted-foreground">{event.event_type}</span>
        </span>
        <time dateTime={event.timestamp} title={new Date(event.timestamp).toLocaleString()} className="shrink-0 text-[11px] text-muted-foreground">{relativeTime(event.timestamp, now)}</time>
        <ChevronRight aria-hidden className={cn("mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-150", open && "rotate-90")} />
      </button>
      {open && (
        <div className="px-4 pb-3 pl-10">
          <div className="mb-2 flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>Source: <span className="text-foreground/90">{event.source}</span></span>
            <span aria-hidden>·</span>
            <span className="truncate font-mono">{event.id}</span>
            <CopyButton value={JSON.stringify(event, null, 2)} label="Copy event JSON" />
          </div>
          <JsonView value={event.payload} />
        </div>
      )}
    </li>
  );
}

/** The retained event history plus live events, newest first, with readable descriptions. */
export function EventStream({ events, agentNames, now }: { events: RealtimeEvent[]; agentNames: Record<string, string>; now: Date }) {
  const [category, setCategory] = useState<EventCategory | "all">("all");
  const [query, setQuery] = useState("");
  const [showRoutine, setShowRoutine] = useState(false);
  const [limit, setLimit] = useState(PAGE);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return events.filter((event) => {
      if (event.event_type === "log.created") return false; // shown under Logs
      if (!showRoutine && isRoutineEvent(event.event_type)) return false;
      if (category !== "all" && eventCategory(event.event_type) !== category) return false;
      if (!needle) return true;
      return `${describeEvent(event, agentNames)} ${event.event_type} ${event.source} ${JSON.stringify(event.payload)}`.toLowerCase().includes(needle);
    });
  }, [agentNames, category, events, query, showRoutine]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
        <div className="relative lg:w-72">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(event) => { setQuery(event.target.value); setLimit(PAGE); }} placeholder="Search events" aria-label="Search events" className="pl-8" />
        </div>
        <div role="group" aria-label="Event type" className="flex flex-wrap gap-1">
          {EVENT_CATEGORIES.map((item) => (
            <button key={item.value} type="button" aria-pressed={category === item.value} onClick={() => { setCategory(item.value); setLimit(PAGE); }}
              className={cn("h-8 rounded-md px-2.5 text-xs font-medium transition-colors", category === item.value ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground")}>
              {item.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground lg:ml-auto">
          <input type="checkbox" checked={showRoutine} onChange={(event) => setShowRoutine(event.target.checked)} className="accent-[var(--color-accent)]" />
          Show heartbeats
        </label>
      </div>
      {visible.length === 0 ? (
        <EmptyState icon={Radio} title={events.length === 0 ? "No events yet" : "No matching events"} description={events.length === 0 ? "Events appear here as Agents run and the system changes." : "Try another search or event type."} />
      ) : (
        <div className="rounded-lg border border-border bg-surface">
          <ul className="max-h-[32rem] divide-y divide-border overflow-y-auto">
            {visible.slice(0, limit).map((event) => <EventRow key={event.id} event={event} agentNames={agentNames} now={now} />)}
          </ul>
          {visible.length > limit && (
            <button type="button" onClick={() => setLimit((value) => value + PAGE)} className="w-full border-t border-border py-2 text-xs text-muted-foreground transition-colors hover:text-foreground">
              Show more ({visible.length - limit} older)
            </button>
          )}
        </div>
      )}
    </div>
  );
}
