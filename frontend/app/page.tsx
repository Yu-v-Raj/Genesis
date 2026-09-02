"use client";

import Link from "next/link";
import { Activity, ArrowUpRight, Bot, CheckCircle2, Clock3, Cpu, Gauge, HeartPulse, Plus, Radio, Server, Wifi, Wrench, Workflow } from "lucide-react";

import { EventStream } from "@/components/dashboard/event-stream";
import { ErrorState } from "@/components/dashboard/error-state";
import { HealthPanel } from "@/components/dashboard/health-panel";
import { LiveLogViewer } from "@/components/dashboard/live-log-viewer";
import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { RealtimeStatus } from "@/components/dashboard/realtime-status";
import { ServicesList, type ServiceStatus } from "@/components/dashboard/services-list";
import { StatsCardSkeleton, StatusCardSkeleton } from "@/components/dashboard/skeletons";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { useMonitoring } from "@/hooks/use-monitoring";
import { useWorkflowSummary } from "@/hooks/use-workflow-summary";

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3_600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3_600)}h ${Math.floor((seconds % 3_600) / 60)}m`;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function serviceStatus(status: string): ServiceStatus {
  if (["online", "up", "healthy", "running", "active"].includes(status.toLowerCase())) return "online";
  if (["warning", "degraded", "partial"].includes(status.toLowerCase())) return "degraded";
  return "offline";
}

export function MonitoringDashboard() {
  const { data, loading, error, connectionStatus, retry } = useMonitoring();
  const runningExecutions = data?.executions.filter((execution) => ["pending", "queued", "starting", "running"].includes(execution.status)) ?? [];
  const completed = data?.executions.filter((execution) => execution.status === "completed") ?? [];
  const terminal = data?.executions.filter((execution) => ["completed", "failed", "cancelled"].includes(execution.status)) ?? [];
  const durations = completed.map((execution) => execution.duration).filter((value): value is number => value !== null);
  const averageDuration = durations.length ? durations.reduce((total, value) => total + value, 0) / durations.length : null;
  const successRate = terminal.length ? `${Math.round((completed.length / terminal.length) * 100)}%` : "—";
  const services = data?.services.map((service) => ({ ...service, status: serviceStatus(service.status) })) ?? [];

  const overview = data ? [
    { label: "Runtime state", value: data.runtime.state, icon: Cpu, tone: "text-primary" },
    { label: "Heartbeat", value: data.lastHeartbeat ? new Date(data.lastHeartbeat).toLocaleTimeString() : "Awaiting", icon: HeartPulse, tone: "text-emerald-300" },
    { label: "Version", value: data.health.version, icon: Server, tone: "text-foreground" },
    { label: "Uptime", value: formatUptime(data.health.uptime), icon: Clock3, tone: "text-primary" },
    { label: "WebSocket", value: connectionStatus, icon: Wifi, tone: connectionStatus === "connected" ? "text-emerald-300" : "text-amber-300" },
  ] : [];
  const statistics = data ? [
    { label: "Running Agents", value: data.agents.filter((agent) => agent.status === "running").length, icon: Bot, tone: "text-emerald-300" },
    { label: "Running Executions", value: runningExecutions.length, icon: Activity, tone: "text-amber-300" },
    { label: "Registered Services", value: data.services.length, icon: Server, tone: "text-primary" },
    { label: "Event Count", value: data.events.length, icon: Radio, tone: "text-foreground" },
    { label: "Execution Count", value: data.executions.length, icon: Gauge, tone: "text-primary" },
    { label: "Connected Clients", value: connectionStatus === "connected" ? 1 : 0, icon: Wifi, tone: "text-emerald-300" },
    { label: "Average Duration", value: formatDuration(averageDuration), icon: Clock3, tone: "text-primary" },
    { label: "Success Rate", value: successRate, icon: CheckCircle2, tone: "text-emerald-300" },
  ] : [];

  return <div className="flex h-screen w-full overflow-hidden"><Sidebar /><div className="flex flex-1 flex-col overflow-hidden"><Topbar /><main id="monitoring" className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8"><div className="mx-auto flex max-w-7xl flex-col gap-7">
    {data && <RealtimeNotifications events={data.events.slice(0, 1)} />}
    <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><div className="flex items-center gap-2"><Activity className="h-5 w-5 text-primary" /><h1 className="text-2xl font-semibold tracking-tight text-foreground">Monitoring</h1></div><p className="mt-1 text-sm text-muted-foreground">The operational control center for Genesis.</p></div><RealtimeStatus connectionStatus={connectionStatus} runtimeState={data?.runtime.state ?? "loading"} lastHeartbeat={data?.lastHeartbeat ?? null} /></header>
    {error && data === null ? <ErrorState message={error} onRetry={() => void retry()} isRetrying={loading} /> : <>
      {error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300"><span>{error}</span><button type="button" onClick={() => void retry()} className="rounded-md border border-red-400/25 px-3 py-1.5 text-xs font-medium text-red-100 transition-colors hover:bg-red-400/10">Retry</button></div>}
      <section><div className="mb-3"><h2 className="text-sm font-semibold text-foreground">Runtime Overview</h2><p className="mt-1 text-xs text-muted-foreground">Current process health and real-time connectivity.</p></div><div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">{loading ? Array.from({ length: 5 }, (_, index) => <StatusCardSkeleton key={index} />) : overview.map(({ label, value, icon: Icon, tone }) => <div key={label} className="rounded-xl border border-border bg-surface p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/15"><div className="flex items-center justify-between"><span className="text-xs font-medium text-muted-foreground">{label}</span><Icon className={`h-4 w-4 ${tone}`} /></div><p className="mt-3 truncate text-lg font-semibold capitalize text-foreground" title={value}>{value}</p></div>)}</div></section>
      <section><div className="mb-3"><h2 className="text-sm font-semibold text-foreground">System Statistics</h2><p className="mt-1 text-xs text-muted-foreground">Calculated from loaded runtime, Agent, and Execution data.</p></div><div className="grid grid-cols-2 gap-3 md:grid-cols-4">{loading ? Array.from({ length: 8 }, (_, index) => <StatsCardSkeleton key={index} />) : statistics.map(({ label, value, icon: Icon, tone }) => <div key={label} className="rounded-xl border border-border bg-surface p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/15"><div className="flex items-center justify-between"><span className="text-xs text-muted-foreground">{label}</span><Icon className={`h-4 w-4 ${tone}`} /></div><p className="mt-2 text-xl font-semibold tracking-tight text-foreground">{value}</p></div>)}</div></section>
      {loading ? <div className="grid gap-5 lg:grid-cols-2"><div className="skeleton-shimmer h-96 rounded-xl border border-border bg-surface" /><div className="skeleton-shimmer h-96 rounded-xl border border-border bg-surface" /></div> : data && <><section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]"><EventStream events={data.events} /><LiveLogViewer events={data.events} /></section><section className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]"><div><div className="mb-3"><h2 className="text-sm font-semibold text-foreground">Registered Services</h2><p className="mt-1 text-xs text-muted-foreground">Hover a service for its operational description.</p></div><ServicesList services={services} /></div><HealthPanel runtimeState={data.runtime.state} websocket={connectionStatus} /></section></>}
    </>}
  </div></main></div></div>;
}

export default function Home() {
  const { data, loading, error, connectionStatus, retry } = useMonitoring();
  const workflowSummary = useWorkflowSummary();
  const quickStatistics = data ? [
    { label: "Running Agents", value: data.agents.filter((agent) => agent.status === "running").length, icon: Bot, tone: "text-emerald-300" },
    { label: "Running Executions", value: data.executions.filter((execution) => ["pending", "queued", "starting", "running"].includes(execution.status)).length, icon: Activity, tone: "text-amber-300" },
    { label: "Registered Tools", value: data.tools.length, icon: Wrench, tone: "text-primary" },
    { label: "Registered Services", value: data.services.length, icon: Server, tone: "text-foreground" },
    { label: "Workflows", value: workflowSummary?.total ?? "—", detail: workflowSummary ? `${workflowSummary.running} running · ${workflowSummary.failed} failed` : "Workflow API unavailable", icon: Workflow, tone: workflowSummary?.failed ? "text-red-300" : "text-primary" },
  ] : [];
  const health = data ? [
    { label: "Runtime", value: data.runtime.state, icon: Cpu, tone: "text-primary" },
    { label: "Health", value: data.health.status, icon: HeartPulse, tone: "text-emerald-300" },
    { label: "Uptime", value: formatUptime(data.health.uptime), icon: Clock3, tone: "text-primary" },
    { label: "WebSocket", value: connectionStatus, icon: Wifi, tone: connectionStatus === "connected" ? "text-emerald-300" : "text-amber-300" },
  ] : [];

  return <div className="flex h-screen w-full overflow-hidden"><Sidebar /><div className="flex flex-1 flex-col overflow-hidden"><Topbar /><main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8"><div className="mx-auto flex max-w-6xl flex-col gap-7">
    {data && <RealtimeNotifications events={data.events.slice(0, 5)} />}
    <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><div className="flex items-center gap-2"><Cpu className="h-5 w-5 text-primary" /><h1 className="text-2xl font-semibold tracking-tight text-foreground">Genesis</h1><span className="rounded-full border border-border bg-surface px-2 py-0.5 text-xs font-medium text-muted-foreground">{data?.health.version ?? "Loading"}</span></div><p className="mt-1 text-sm text-muted-foreground">Your AI Agent Operating System — what is happening right now.</p></div><RealtimeStatus connectionStatus={connectionStatus} runtimeState={data?.runtime.state ?? "loading"} lastHeartbeat={data?.lastHeartbeat ?? null} /></header>
    {error && data === null ? <ErrorState message={error} onRetry={() => void retry()} isRetrying={loading} /> : <>
      {error && <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300"><span>{error}</span><button type="button" onClick={() => void retry()} className="rounded-md border border-red-400/25 px-3 py-1.5 text-xs font-medium text-red-100 transition-colors hover:bg-red-400/10">Retry</button></div>}
      <section><h2 className="mb-3 text-sm font-semibold text-foreground">Quick Health</h2><div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{loading ? Array.from({ length: 4 }, (_, index) => <StatusCardSkeleton key={index} />) : health.map(({ label, value, icon: Icon, tone }) => <div key={label} className="rounded-xl border border-border bg-surface p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/15"><div className="flex items-center justify-between"><span className="text-xs text-muted-foreground">{label}</span><Icon className={`h-4 w-4 ${tone}`} /></div><p className="mt-2 truncate text-xl font-semibold capitalize text-foreground">{value}</p></div>)}</div></section>
      <section><h2 className="mb-3 text-sm font-semibold text-foreground">Quick Statistics</h2><div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{loading ? Array.from({ length: 4 }, (_, index) => <StatsCardSkeleton key={index} />) : quickStatistics.map(({ label, value, icon: Icon, tone, detail }) => <div key={label} className="rounded-xl border border-border bg-surface p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/15"><div className="flex items-center justify-between"><span className="text-xs text-muted-foreground">{label}</span><Icon className={`h-4 w-4 ${tone}`} /></div><p className="mt-2 text-xl font-semibold text-foreground">{value}</p>{detail && <p className="mt-1 text-[11px] text-muted-foreground">{detail}</p>}</div>)}</div></section>
      <section className="grid gap-5 lg:grid-cols-2"><div className="rounded-xl border border-border bg-surface p-5 shadow-sm"><h2 className="text-sm font-semibold text-foreground">Recent Activity</h2><p className="mt-1 text-xs text-muted-foreground">The latest activity across Genesis.</p><div className="mt-4 divide-y divide-border">{data?.events.slice(0, 8).map((event) => <div key={event.id} className="flex items-center justify-between gap-3 py-3"><div className="min-w-0"><p className="truncate text-xs font-medium text-foreground">{event.event_type.replaceAll(".", " ")}</p><p className="mt-1 truncate text-xs text-muted-foreground">{event.source}</p></div><time className="shrink-0 text-[11px] text-muted-foreground">{new Date(event.timestamp).toLocaleTimeString()}</time></div>) ?? <p className="py-8 text-center text-sm text-muted-foreground">Waiting for recent activity.</p>}</div></div><div className="rounded-xl border border-border bg-surface p-5 shadow-sm"><h2 className="text-sm font-semibold text-foreground">Quick Actions</h2><p className="mt-1 text-xs text-muted-foreground">Jump straight into common Genesis workflows.</p><div className="mt-4 grid gap-2 sm:grid-cols-2"><QuickAction href="/agents" icon={Plus} label="Create Agent" /><QuickAction href="/agents" icon={Bot} label="Open Agents" /><QuickAction href="/monitoring" icon={Activity} label="Open Monitoring" /><span title="The Tools page is not enabled in the current frontend."><button type="button" disabled className="flex w-full items-center justify-between rounded-lg border border-border px-3 py-2.5 text-left text-xs font-medium text-muted-foreground opacity-55"><span className="flex items-center gap-2"><Wrench className="h-3.5 w-3.5" />Open Tools</span><ArrowUpRight className="h-3.5 w-3.5" /></button></span></div></div></section>
    </>}
  </div></main></div></div>;
}

function QuickAction({ href, icon: Icon, label }: { href: string; icon: typeof Activity; label: string }) { return <Link href={href} className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5 text-xs font-medium text-foreground transition-all hover:-translate-y-0.5 hover:bg-white/[0.05]"><span className="flex items-center gap-2"><Icon className="h-3.5 w-3.5 text-primary" />{label}</span><ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" /></Link>; }
