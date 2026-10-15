"use client";

import { useMemo, useState } from "react";
import { ChevronRight, Radio, Search, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { JsonView } from "@/components/ui/disclosure";
import { EmptyState } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/field";
import { cn } from "@/lib/utils";
import type { RealtimeEvent } from "@/types/realtime";

const LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] as const;
type LevelFilter = (typeof LEVELS)[number];

const LEVEL_TONES: Record<string, string> = { DEBUG: "tone-running", INFO: "tone-info", WARNING: "tone-warning", ERROR: "tone-danger", CRITICAL: "tone-danger" };

function level(event: RealtimeEvent): string {
  return typeof event.payload.level === "string" ? event.payload.level : "INFO";
}

function message(event: RealtimeEvent): string {
  return typeof event.payload.message === "string" ? event.payload.message : "Log event";
}

function LogRow({ event }: { event: RealtimeEvent }) {
  const [open, setOpen] = useState(false);
  const context = event.payload.context;
  const hasContext = context !== undefined && context !== null && !(typeof context === "object" && Object.keys(context).length === 0);
  return (
    <li className="px-4 py-2">
      <div className="flex items-start gap-3 text-xs">
        <span className={cn("w-16 shrink-0 font-mono text-[11px] font-medium tone-fg", LEVEL_TONES[level(event)] ?? "tone-neutral")}>{level(event)}</span>
        <span className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-foreground">{message(event)}</span>
        <time dateTime={event.timestamp} className="shrink-0 text-[11px] text-muted-foreground">{new Date(event.timestamp).toLocaleTimeString()}</time>
        <CopyButton value={`${level(event)} ${message(event)}`} label="Copy log line" />
        {hasContext && (
          <button type="button" aria-expanded={open} aria-label={open ? "Hide log details" : "Show log details"} onClick={() => setOpen((value) => !value)} className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-white/[0.06] hover:text-foreground">
            <ChevronRight aria-hidden className={cn("h-3.5 w-3.5 transition-transform duration-150", open && "rotate-90")} />
          </button>
        )}
      </div>
      {open && hasContext && <div className="mt-2 pl-[4.75rem]"><JsonView value={context} /></div>}
    </li>
  );
}

/** Structured log events (`log.created`) from the retained history plus live updates, newest first. */
export function LogViewer({ events }: { events: RealtimeEvent[] }) {
  const [filter, setFilter] = useState<LevelFilter>("ALL");
  const [query, setQuery] = useState("");
  const [clearedIds, setClearedIds] = useState<Set<string>>(new Set());

  const all = useMemo(() => events.filter((event) => event.event_type === "log.created"), [events]);
  const logs = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return all.filter((event) =>
      !clearedIds.has(event.id) &&
      (filter === "ALL" || level(event) === filter) &&
      `${level(event)} ${message(event)} ${event.source}`.toLowerCase().includes(needle));
  }, [all, clearedIds, filter, query]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative sm:w-72">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search logs" aria-label="Search logs" className="pl-8" />
        </div>
        <Select value={filter} onChange={(event) => setFilter(event.target.value as LevelFilter)} aria-label="Log level" className="sm:w-40">
          {LEVELS.map((value) => <option key={value} value={value}>{value === "ALL" ? "All levels" : value}</option>)}
        </Select>
        <Button size="sm" variant="ghost" icon={<Trash2 aria-hidden className="h-3.5 w-3.5" />} onClick={() => setClearedIds(new Set(all.map((event) => event.id)))} className="sm:ml-auto" title="Hide the current lines in this view; nothing is deleted on the server">
          Clear view
        </Button>
      </div>
      {logs.length === 0 ? (
        <EmptyState icon={Radio} title={all.length === 0 ? "No log entries yet" : "No matching log entries"} description={all.length === 0 ? "Structured log entries recorded since the backend started appear here." : "Try another search or level."} />
      ) : (
        <ul className="max-h-[32rem] divide-y divide-border overflow-y-auto rounded-lg border border-border bg-surface">
          {logs.map((event) => <LogRow key={event.id} event={event} />)}
        </ul>
      )}
    </div>
  );
}
