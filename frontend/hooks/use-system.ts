"use client";

import { useCallback, useEffect, useState } from "react";

import type { ActivityItem } from "@/components/dashboard/recent-activity";
import type {
  ServiceItem,
  ServiceStatus,
} from "@/components/dashboard/services-list";
import type { StatsCardData } from "@/components/dashboard/stats-card";
import type { StatusCardData } from "@/components/dashboard/status-card";
import { useRealtime } from "@/hooks/use-realtime";
import { SystemApiError, SystemService } from "@/services/system.service";
import type { ConnectionStatus, RealtimeEvent } from "@/types/realtime";

export interface DashboardViewData {
  statusCards: StatusCardData[];
  services: ServiceItem[];
  stats: StatsCardData[];
  activity: ActivityItem[];
  events: RealtimeEvent[];
  runtimeState: string;
  lastHeartbeat: string | null;
}

function normalizeServiceStatus(rawStatus: string): ServiceStatus {
  const value = rawStatus.trim().toLowerCase();
  if (["online", "up", "healthy", "running", "active"].includes(value)) return "online";
  if (["degraded", "warning", "partial"].includes(value)) return "degraded";
  return "offline";
}

function eventTitle(event: RealtimeEvent): string {
  return event.event_type
    .split(".")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function stringPayloadValue(event: RealtimeEvent, key: string): string | null {
  const value = event.payload[key];
  return typeof value === "string" ? value : null;
}

function updateServiceSummary(cards: StatusCardData[], services: ServiceItem[]): StatusCardData[] {
  const activeCount = services.filter((service) => service.status === "online").length;
  return cards.map((card) =>
    card.title === "Services"
      ? {
          ...card,
          value: `${activeCount} Active`,
          description: `${services.length} services registered.`,
        }
      : card
  );
}

function applyRealtimeEvent(data: DashboardViewData, event: RealtimeEvent): DashboardViewData {
  let services = data.services;
  const serviceName = stringPayloadValue(event, "service");
  if (event.event_type === "service.registered" && serviceName) {
    if (!services.some((service) => service.name === serviceName)) {
      services = [
        ...services,
        { name: serviceName, description: "Genesis Core service.", status: "online" },
      ];
    }
  } else if (event.event_type === "service.removed" && serviceName) {
    services = services.filter((service) => service.name !== serviceName);
  }

  const runtimeState =
    event.event_type === "system.heartbeat"
      ? stringPayloadValue(event, "runtime_state") ?? data.runtimeState
      : event.event_type === "system.started"
        ? "running"
        : event.event_type === "system.stopped"
          ? "stopped"
          : data.runtimeState;
  const statusCards = updateServiceSummary(
    data.statusCards.map((card) =>
      card.title === "Runtime" ? { ...card, value: runtimeState } : card
    ),
    services
  );

  return {
    ...data,
    services,
    statusCards,
    activity: [
      {
        id: event.id,
        title: eventTitle(event),
        timestamp: new Date(event.timestamp).toLocaleTimeString(),
      },
      ...data.activity,
    ].slice(0, 50),
    events: [event, ...data.events].slice(0, 100),
    runtimeState,
    lastHeartbeat: event.event_type === "system.heartbeat" ? event.timestamp : data.lastHeartbeat,
  };
}

export function useSystemDashboard(): {
  data: DashboardViewData | null;
  loading: boolean;
  error: string | null;
  connectionStatus: ConnectionStatus;
} {
  const [data, setData] = useState<DashboardViewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { connectionStatus, latestEvent } = useRealtime();

  const loadInitialDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [health, runtime, services, tools, plugins, memory, workflows] = await Promise.all([
        SystemService.getHealth(),
        SystemService.getRuntime(),
        SystemService.getServices(),
        SystemService.getTools(),
        SystemService.getPlugins(),
        SystemService.getMemory(),
        SystemService.getWorkflows(),
      ]);
      const mappedServices: ServiceItem[] = services.services.map((service) => ({
        name: service.name,
        description: service.description,
        status: normalizeServiceStatus(service.status),
      }));
      const activeServiceCount = mappedServices.filter((service) => service.status === "online").length;

      setData({
        statusCards: [
          {
            icon: "server",
            title: "Runtime",
            value: runtime.state,
            description: "Current state of the Genesis runtime.",
          },
          {
            icon: "heartPulse",
            title: "Health",
            value: health.status,
            description: `Version ${health.version} • Uptime ${health.uptime}`,
          },
          {
            icon: "activity",
            title: "Services",
            value: `${activeServiceCount} Active`,
            description: `${mappedServices.length} services registered.`,
          },
          {
            icon: "tag",
            title: "Version",
            value: health.version,
            description: "Current Genesis runtime version.",
          },
        ],
        services: mappedServices,
        stats: [
          { icon: "wrench", label: "Tools", value: tools.tools.length.toString() },
          { icon: "puzzle", label: "Plugins", value: plugins.plugins.length.toString() },
          { icon: "brainCircuit", label: "Memory Providers", value: memory.providers.length.toString() },
          { icon: "workflow", label: "Workflows", value: workflows.workflows.length.toString() },
        ],
        activity: [],
        events: [],
        runtimeState: runtime.state,
        lastHeartbeat: null,
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof SystemApiError
          ? caughtError.message
          : "An unexpected error occurred while loading the Genesis dashboard."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadInitialDashboard();
  }, [loadInitialDashboard]);

  useEffect(() => {
    if (latestEvent === null) return;
    setData((currentData) =>
      currentData === null ? currentData : applyRealtimeEvent(currentData, latestEvent)
    );
  }, [latestEvent]);

  return { data, loading, error, connectionStatus };
}
