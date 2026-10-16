"use client";

import { useCallback, useEffect, useState } from "react";

import { AgentService } from "@/services/agent.service";
import { EventHistoryService } from "@/services/event-history.service";
import { ExecutionService } from "@/services/execution.service";
import { SystemApiError, SystemService } from "@/services/system.service";
import { useRealtime } from "@/hooks/use-realtime";
import type { Agent } from "@/types/agents";
import type { Execution } from "@/types/executions";
import type { RealtimeEvent } from "@/types/realtime";
import type { HealthApiResponse, PluginApiItem, RuntimeApiResponse, ServiceApiItem } from "@/types/system";
import type { ToolApiItem } from "@/types/system";

export interface MonitoringData {
  health: HealthApiResponse;
  runtime: RuntimeApiResponse;
  services: ServiceApiItem[];
  tools: ToolApiItem[];
  agents: Agent[];
  executions: Execution[];
  /** Pass to ExecutionService.list to load executions older than the newest page. */
  executionsNextBefore: string | null;
  events: RealtimeEvent[];
  /** `null` when the plugin list could not be loaded; it is optional for this view. */
  plugins: PluginApiItem[] | null;
  lastHeartbeat: string | null;
}

export interface MonitoringOptions {
  /** How many retained events to load (1–1000); live events are merged up to this size. */
  eventLimit?: number;
}

function errorMessage(error: unknown): string {
  return error instanceof SystemApiError
    ? error.message
    : "Unable to load Genesis monitoring data. Verify that the backend is available.";
}

function upsertEvent(events: RealtimeEvent[], event: RealtimeEvent, cap: number): RealtimeEvent[] {
  if (events.some((current) => current.id === event.id)) return events;
  return [event, ...events].slice(0, cap);
}

/** Loads operational snapshots and merges live events from one shared WebSocket client. */
export function useMonitoring({ eventLimit = 100 }: MonitoringOptions = {}): {
  data: MonitoringData | null;
  loading: boolean;
  error: string | null;
  connectionStatus: ReturnType<typeof useRealtime>["connectionStatus"];
  retry: () => Promise<void>;
} {
  const [data, setData] = useState<MonitoringData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { connectionStatus, latestEvent } = useRealtime();
  const eventCap = Math.max(250, eventLimit);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [health, runtime, services, tools, agents, executions, history, plugins] = await Promise.all([
        SystemService.getHealth(),
        SystemService.getRuntime(),
        SystemService.getServices(),
        SystemService.getTools(),
        AgentService.list(),
        ExecutionService.list(),
        EventHistoryService.recent(eventLimit),
        SystemService.getPlugins().then((response) => response.plugins).catch(() => null),
      ]);
      const heartbeat = history.events.find((event) => event.event_type === "system.heartbeat");
      setData({
        health,
        runtime,
        services: services.services,
        tools: tools.tools,
        agents: agents.agents,
        executions: executions.executions,
        executionsNextBefore: executions.next_before ?? null,
        events: history.events,
        plugins,
        lastHeartbeat: heartbeat?.timestamp ?? null,
      });
    } catch (caughtError) {
      setError(errorMessage(caughtError));
    } finally {
      setLoading(false);
    }
  }, [eventLimit]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  useEffect(() => {
    if (latestEvent === null) return;
    queueMicrotask(() => setData((current) => {
      if (current === null) return current;
      const next = { ...current, events: upsertEvent(current.events, latestEvent, eventCap) };
      if (latestEvent.event_type === "system.heartbeat") {
        return { ...next, lastHeartbeat: latestEvent.timestamp, runtime: { state: "running" } };
      }
      if (latestEvent.event_type === "system.stopped") {
        return { ...next, runtime: { state: "stopped" } };
      }
      return next;
    }));
    if (latestEvent.event_type.startsWith("agent.") || latestEvent.event_type.startsWith("execution.")) {
      void Promise.all([AgentService.list(), ExecutionService.list()])
        .then(([agents, executions]) => setData((current) => current === null ? current : { ...current, agents: agents.agents, executions: executions.executions, executionsNextBefore: executions.next_before ?? null }))
        .catch(() => undefined);
    }
    if (latestEvent.event_type === "service.registered" || latestEvent.event_type === "service.removed") {
      void SystemService.getServices()
        .then((services) => setData((current) => current === null ? current : { ...current, services: services.services }))
        .catch(() => undefined);
    }
  }, [latestEvent, eventCap]);

  return { data, loading, error, connectionStatus, retry: load };
}
