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
import type { HealthApiResponse, RuntimeApiResponse, ServiceApiItem } from "@/types/system";

export interface MonitoringData {
  health: HealthApiResponse;
  runtime: RuntimeApiResponse;
  services: ServiceApiItem[];
  agents: Agent[];
  executions: Execution[];
  events: RealtimeEvent[];
  lastHeartbeat: string | null;
}

function errorMessage(error: unknown): string {
  return error instanceof SystemApiError
    ? error.message
    : "Unable to load Genesis monitoring data. Verify that the backend is available.";
}

function upsertEvent(events: RealtimeEvent[], event: RealtimeEvent): RealtimeEvent[] {
  if (events.some((current) => current.id === event.id)) return events;
  return [event, ...events].slice(0, 250);
}

/** Loads operational snapshots and merges live events from one shared WebSocket client. */
export function useMonitoring(): {
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [health, runtime, services, agents, executions, history] = await Promise.all([
        SystemService.getHealth(),
        SystemService.getRuntime(),
        SystemService.getServices(),
        AgentService.list(),
        ExecutionService.list(),
        EventHistoryService.recent(),
      ]);
      const heartbeat = history.events.find((event) => event.event_type === "system.heartbeat");
      setData({
        health,
        runtime,
        services: services.services,
        agents: agents.agents,
        executions: executions.executions,
        events: history.events,
        lastHeartbeat: heartbeat?.timestamp ?? null,
      });
    } catch (caughtError) {
      setError(errorMessage(caughtError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (latestEvent === null) return;
    setData((current) => {
      if (current === null) return current;
      const next = { ...current, events: upsertEvent(current.events, latestEvent) };
      if (latestEvent.event_type === "system.heartbeat") {
        return { ...next, lastHeartbeat: latestEvent.timestamp, runtime: { state: "running" } };
      }
      if (latestEvent.event_type === "system.stopped") {
        return { ...next, runtime: { state: "stopped" } };
      }
      return next;
    });
    if (latestEvent.event_type.startsWith("agent.") || latestEvent.event_type.startsWith("execution.")) {
      void Promise.all([AgentService.list(), ExecutionService.list()])
        .then(([agents, executions]) => setData((current) => current === null ? current : { ...current, agents: agents.agents, executions: executions.executions }))
        .catch(() => undefined);
    }
    if (latestEvent.event_type === "service.registered" || latestEvent.event_type === "service.removed") {
      void SystemService.getServices()
        .then((services) => setData((current) => current === null ? current : { ...current, services: services.services }))
        .catch(() => undefined);
    }
  }, [latestEvent]);

  return { data, loading, error, connectionStatus, retry: load };
}
