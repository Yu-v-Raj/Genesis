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
  "memory.retrieved",
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

  if (notifications.length === 0) return null;

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
      "memory.retrieved": "Memory retrieved",
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
    if (event.event_type === "error.occurred" || event.event_type === "execution.failed" || event.event_type === "tool.failed" || event.event_type === "workflow.failed" || event.event_type === "workflow.task.failed") return <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-300" />;
    if (event.event_type === "execution.cancelled") return <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />;
    if (event.event_type === "execution.completed" || event.event_type === "tool.completed" || event.event_type === "workflow.completed" || event.event_type === "workflow.task.completed") return <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />;
    if (event.event_type.startsWith("agent.")) return <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />;
    return <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />;
  }

  return (
    <div className="fixed right-4 top-4 z-50 flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2 sm:right-5 sm:top-5 sm:w-80">
      <AnimatePresence initial={false}>
      {notifications.map((event) => (
        <motion.div key={event.id} initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, x: 12, scale: 0.98 }} transition={{ duration: 0.18 }} className="flex gap-3 rounded-xl border border-border bg-surface/95 p-3.5 shadow-xl shadow-black/20 backdrop-blur">
          {notificationIcon(event)}
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-foreground">
              {notificationTitle(event)}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">Received from {event.source}</p>
          </div>
          <button type="button" onClick={() => dismiss(event.id)} className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground" aria-label="Dismiss notification"><X className="h-3.5 w-3.5" /></button>
        </motion.div>
      ))}
      </AnimatePresence>
    </div>
  );
}
