"use client";

import { Puzzle, Server } from "lucide-react";

import { EmptyState } from "@/components/ui/feedback";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatUptime, relativeTime } from "@/lib/operations";
import type { MonitoringData } from "@/hooks/use-monitoring";
import type { ConnectionStatus } from "@/types/realtime";

/** Service status words vary by service; group them into online / degraded / offline. */
function serviceStatus(status: string): "online" | "degraded" | "offline" {
  const value = status.toLowerCase();
  if (["online", "up", "healthy", "running", "active"].includes(value)) return "online";
  if (["warning", "degraded", "partial"].includes(value)) return "degraded";
  return "offline";
}

/** A running process is healthy, not "work in progress", so it gets the online tone. */
function ProcessState({ state }: { state: string }) {
  return state === "running" ? <StatusBadge status="online" label="Running" /> : <StatusBadge status={state} />;
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm text-foreground">{children}</dd>
    </div>
  );
}

/** Runtime health, registered services and plugins, exactly as the backend reports them. */
export function SystemPanel({ data, connectionStatus, now }: { data: MonitoringData; connectionStatus: ConnectionStatus; now: Date }) {
  return (
    <div className="flex flex-col gap-5">
      <Panel>
        <PanelHeader title="Runtime" description="The Genesis backend process and this page's live connection." />
        <dl className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-6">
          <Fact label="Runtime"><ProcessState state={data.runtime.state} /></Fact>
          <Fact label="Health"><ProcessState state={data.health.status} /></Fact>
          <Fact label="Live updates"><StatusBadge status={connectionStatus} /></Fact>
          <Fact label="Last heartbeat">{data.lastHeartbeat ? relativeTime(data.lastHeartbeat, now) : "Waiting"}</Fact>
          <Fact label="Uptime">{formatUptime(data.health.uptime)}</Fact>
          <Fact label="Version"><span className="font-mono text-xs">v{data.health.version}</span></Fact>
        </dl>
      </Panel>

      <Panel>
        <PanelHeader title="Services" description={`${data.services.length} registered with the runtime.`} />
        {data.services.length === 0 ? (
          <EmptyState icon={Server} title="No services registered" className="m-4" />
        ) : (
          <ul className="grid gap-px overflow-hidden bg-border sm:grid-cols-2">
            {data.services.map((service) => (
              <li key={service.name} className="flex items-start justify-between gap-3 bg-surface px-4 py-3">
                <span className="min-w-0">
                  <span className="block truncate text-sm text-foreground">{service.name}</span>
                  <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{service.description}</span>
                </span>
                <StatusBadge status={serviceStatus(service.status)} className="shrink-0" />
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel>
        <PanelHeader title="Plugins" />
        {data.plugins === null ? (
          <p className="p-4 text-sm text-muted-foreground">The plugin list couldn&apos;t be loaded.</p>
        ) : data.plugins.length === 0 ? (
          <EmptyState icon={Puzzle} title="No plugins installed" description="Genesis doesn't have any plugins registered right now." className="m-4 border-none" />
        ) : (
          <ul className="divide-y divide-border">
            {data.plugins.map((plugin) => (
              <li key={plugin.name} className="flex items-start justify-between gap-3 px-4 py-3">
                <span className="min-w-0"><span className="block text-sm text-foreground">{plugin.name}</span><span className="block text-xs text-muted-foreground">{plugin.description}</span></span>
                <StatusBadge status={plugin.status} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
