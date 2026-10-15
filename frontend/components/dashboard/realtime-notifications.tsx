"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, CircleAlert, Info, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import type { RealtimeEvent } from "@/types/realtime";

const DEFAULT_DISMISS_AFTER_MS = 5_000;
const MAX_REMEMBERED_NOTIFICATION_IDS = 500;
const NOTIFIABLE_EVENTS = new Set([
  "plugin.loaded",
  "workflow.registered",
  "workflow.created",
  "workflow.queued",
  "workflow.started",
  "workflow.paused",
  "workflow.resumed",
  "workflow.completed",
  "workflow.failed",
  "workflow.cancelled",
  "workflow.task.ready",
  "workflow.task.started",
  "workflow.task.completed",
  "workflow.task.failed",
  "memory_provider.registered",
  "memory.created",
  "memory.updated",
  "memory.deleted",
  "error.occurred",
  "agent.created",
  "agent.started",
  "agent.paused",
  "agent.resumed",
  "agent.stopped",
  "agent.deleted",
  "execution.created",
  "execution.queued",
  "execution.started",
  "execution.completed",
  "execution.failed",
  "execution.cancelled",
  "tool.executed",
  "tool.completed",
  "tool.failed",
]);

interface RealtimeNotificationsProps {
  events: RealtimeEvent[];
  dismissAfterMs?: number;
}

export function RealtimeNotifications({
  events,
  dismissAfterMs = DEFAULT_DISMISS_AFTER_MS,
}: RealtimeNotificationsProps) {
  const [notifications, setNotifications] = useState<RealtimeEvent[]>([]);
  const timersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const seenIdsRef = useRef(new Set<string>());
  const seenOrderRef = useRef<string[]>([]);

  const dismiss = useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer !== undefined) clearTimeout(timer);
    timersRef.current.delete(id);
    setNotifications((current) => current.filter((notification) => notification.id !== id));
  }, []);

  useEffect(() => {
    const additions = events.filter((event) => {
      if (!NOTIFIABLE_EVENTS.has(event.event_type) || seenIdsRef.current.has(event.id)) {
        return false;
      }
      seenIdsRef.current.add(event.id);
      seenOrderRef.current.push(event.id);
      if (seenOrderRef.current.length > MAX_REMEMBERED_NOTIFICATION_IDS) {
        const oldestId = seenOrderRef.current.shift();
        if (oldestId !== undefined) seenIdsRef.current.delete(oldestId);
      }
      return true;
    });
    if (additions.length === 0) return;

    setNotifications((current) => [...current, ...additions]);
    if (dismissAfterMs > 0) {
      for (const event of additions) {
        timersRef.current.set(event.id, setTimeout(() => dismiss(event.id), dismissAfterMs));
      }
    }
  }, [dismiss, dismissAfterMs, events]);

  useEffect(() => () => {
    for (const timer of timersRef.current.values()) clearTimeout(timer);
    timersRef.current.clear();
  }, []);

  function notificationTitle(event: RealtimeEvent): string {
    const titles: Record<string, string> = {
      "execution.created": "Execution created",
      "execution.queued": "Execution queued",
      "execution.started": "Execution started",
      "execution.completed": "Execution completed successfully",
      "execution.failed": "Execution failed",
      "execution.cancelled": "Execution cancelled",
      "tool.executed": "Tool execution started",
      "tool.completed": "Tool execution completed",
      "tool.failed": "Tool execution failed",
      "memory.created": "Memory created",
      "memory.updated": "Memory updated",
      "memory.deleted": "Memory deleted",
      "workflow.created": "Workflow created",
      "workflow.queued": "Workflow queued",
      "workflow.started": "Workflow started",
      "workflow.paused": "Workflow paused",
      "workflow.resumed": "Workflow resumed",
      "workflow.completed": "Workflow completed successfully",
      "workflow.failed": "Workflow failed",
      "workflow.cancelled": "Workflow cancelled",
      "workflow.task.ready": "Workflow task ready",
      "workflow.task.started": "Workflow task started",
      "workflow.task.completed": "Workflow task completed",
      "workflow.task.failed": "Workflow task failed",
    };
    return titles[event.event_type] ?? event.event_type.replaceAll(".", " ");
  }

  function notificationIcon(event: RealtimeEvent) {
    if (event.event_type === "error.occurred" || event.event_type.endsWith(".failed")) return <CircleAlert aria-hidden className="tone-danger tone-fg mt-0.5 h-4 w-4 shrink-0" />;
    if (event.event_type.endsWith(".cancelled")) return <Info aria-hidden className="tone-warning tone-fg mt-0.5 h-4 w-4 shrink-0" />;
    if (event.event_type.endsWith(".completed") || event.event_type.startsWith("agent.")) return <CheckCircle2 aria-hidden className="tone-success tone-fg mt-0.5 h-4 w-4 shrink-0" />;
    return <Info aria-hidden className="tone-info tone-fg mt-0.5 h-4 w-4 shrink-0" />;
  }

  return (
    // Top-right, just below the top bar so its search and version stay visible, and clear of the
    // conversation composer at the bottom of the Agents page.
    <div role="status" aria-live="polite" className="pointer-events-none fixed right-4 top-[4.25rem] z-40 flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2 sm:right-5 sm:w-80">
      <AnimatePresence initial={false}>
      {notifications.map((event) => (
        <motion.div key={event.id} initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, x: 12, scale: 0.98 }} transition={{ duration: 0.18 }} className="pointer-events-auto flex gap-3 rounded-lg border border-border bg-elevated/95 p-3 shadow-overlay backdrop-blur">
          {notificationIcon(event)}
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-foreground">{notificationTitle(event)}</p>
            <time dateTime={event.timestamp} className="mt-0.5 block text-[11px] text-muted-foreground">{new Date(event.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</time>
          </div>
          <button type="button" onClick={() => dismiss(event.id)} className="-m-1 flex h-7 w-7 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground pointer-coarse:h-10 pointer-coarse:w-10" aria-label="Dismiss notification"><X aria-hidden className="h-3.5 w-3.5" /></button>
        </motion.div>
      ))}
      </AnimatePresence>
    </div>
  );
}
