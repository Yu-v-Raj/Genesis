"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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
  const containerRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const logs = useMemo(
    () =>
      events
        .filter(
          (event) =>
            event.event_type === "log.created" &&
            (filter === "ALL" || getLogLevel(event) === filter)
        )
        .reverse(),
    [events, filter]
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
        <span className="text-sm font-medium text-foreground">Live Logs</span>
        <select
          value={filter}
          onChange={(event) => {
            if (isLogLevelFilter(event.target.value)) setFilter(event.target.value);
          }}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground"
          aria-label="Filter live logs by level"
        >
          {LOG_LEVELS.map((level) => (
            <option key={level} value={level}>
              {level}
            </option>
          ))}
        </select>
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
              <span className="w-16 shrink-0 font-medium text-primary">{getLogLevel(event)}</span>
              <span className="flex-1 text-foreground">{getLogMessage(event)}</span>
              <span className="shrink-0 text-muted-foreground">
                {new Date(event.timestamp).toLocaleTimeString()}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
