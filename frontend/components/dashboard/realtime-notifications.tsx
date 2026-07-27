"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";

import type { RealtimeEvent } from "@/types/realtime";

const DEFAULT_DISMISS_AFTER_MS = 5_000;
const MAX_REMEMBERED_NOTIFICATION_IDS = 500;
const NOTIFIABLE_EVENTS = new Set([
  "plugin.loaded",
  "workflow.registered",
  "memory_provider.registered",
  "error.occurred",
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

  return (
    <div className="fixed right-5 top-5 z-50 flex w-80 flex-col gap-2">
      {notifications.map((event) => (
        <div key={event.id} className="flex gap-2 rounded-md border border-border bg-surface p-3 shadow-lg">
          <Bell className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <div>
            <p className="text-xs font-medium text-foreground">
              {event.event_type.replaceAll(".", " ")}
            </p>
            <p className="text-xs text-muted-foreground">Received from {event.source}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
