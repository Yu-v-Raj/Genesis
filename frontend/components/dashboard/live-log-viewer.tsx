"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Copy, Search, Trash2 } from "lucide-react";

import type { RealtimeEvent } from "@/types/realtime";

const LOG_LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] as const;
const AUTO_SCROLL_THRESHOLD_PX = 32;
type LogLevelFilter = (typeof LOG_LEVELS)[number];

interface LiveLogViewerProps {
  events: RealtimeEvent[];
}

function getLogLevel(event: RealtimeEvent): string {
  const level = event.payload.level;
  return typeof level === "string" ? level : "INFO";
}

function getLogMessage(event: RealtimeEvent): string {
  const message = event.payload.message;
  return typeof message === "string" ? message : "Log event";
}

function isLogLevelFilter(value: string): value is LogLevelFilter {
  return LOG_LEVELS.some((level) => level === value);
}

export function LiveLogViewer({ events }: LiveLogViewerProps) {
  const [filter, setFilter] = useState<LogLevelFilter>("ALL");
  const [query, setQuery] = useState("");
  const [clearedIds, setClearedIds] = useState<Set<string>>(new Set());
  const containerRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const logs = useMemo(
    () =>
      events
        .filter(
          (event) =>
            event.event_type === "log.created" &&
            (filter === "ALL" || getLogLevel(event) === filter) &&
            !clearedIds.has(event.id) &&
            `${getLogLevel(event)} ${getLogMessage(event)} ${event.source}`
              .toLowerCase()
              .includes(query.trim().toLowerCase())
        ),
    [clearedIds, events, filter, query]
  );

  useEffect(() => {
    const container = containerRef.current;
    if (container !== null && shouldAutoScrollRef.current) {
      container.scrollTop = container.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="rounded-lg border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
        <span className="text-sm font-medium text-foreground">Structured Logs</span>
        <div className="flex flex-wrap items-center gap-2"><label className="flex items-center gap-1.5 rounded border border-border bg-background px-2 py-1"><Search className="h-3 w-3 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} className="w-28 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground" placeholder="Search logs" /></label><select value={filter} onChange={(event) => { if (isLogLevelFilter(event.target.value)) setFilter(event.target.value); }} className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground" aria-label="Filter live logs by level">{LOG_LEVELS.map((level) => <option key={level} value={level}>{level}</option>)}</select><button type="button" onClick={() => setClearedIds(new Set(events.filter((event) => event.event_type === "log.created").map((event) => event.id)))} className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"><Trash2 className="h-3 w-3" /> Clear local</button></div>
      </div>
      <div
        ref={containerRef}
        onScroll={(event) => {
          const { clientHeight, scrollHeight, scrollTop } = event.currentTarget;
          shouldAutoScrollRef.current = scrollHeight - scrollTop - clientHeight <= AUTO_SCROLL_THRESHOLD_PX;
        }}
        className="max-h-64 overflow-y-auto divide-y divide-border"
      >
        {logs.length === 0 ? (
          <p className="px-4 py-6 text-xs text-muted-foreground">No matching live logs yet.</p>
        ) : (
          logs.map((event) => (
            <div key={event.id} className="flex gap-3 px-4 py-2 text-xs">
              <span className={`w-16 shrink-0 font-medium ${logLevelColor(getLogLevel(event))}`}>{getLogLevel(event)}</span>
              <span className="flex-1 text-foreground">{getLogMessage(event)}</span>
              <span className="shrink-0 text-muted-foreground">
                {new Date(event.timestamp).toLocaleTimeString()}
              </span>
              <button type="button" onClick={() => void navigator.clipboard?.writeText(`${getLogLevel(event)} ${getLogMessage(event)}`)} className="shrink-0 text-muted-foreground transition-colors hover:text-foreground" aria-label="Copy log"><Copy className="h-3.5 w-3.5" /></button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function logLevelColor(level: string): string {
  if (level === "ERROR" || level === "CRITICAL") return "text-red-300";
  if (level === "WARNING") return "text-amber-300";
  if (level === "DEBUG") return "text-violet-300";
  return "text-emerald-300";
}
