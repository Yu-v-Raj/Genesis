import { Activity, CircleAlert, CircleCheck, WifiOff } from "lucide-react";

import type { ConnectionStatus } from "@/types/realtime";

type HealthTone = "healthy" | "warning" | "offline";

function HealthItem({ label, tone }: { label: string; tone: HealthTone }) {
  const Icon = tone === "healthy" ? CircleCheck : tone === "warning" ? CircleAlert : WifiOff;
  const styles: Record<HealthTone, string> = { healthy: "border-emerald-400/20 bg-emerald-400/5 text-emerald-200", warning: "border-amber-400/20 bg-amber-400/5 text-amber-200", offline: "border-red-400/20 bg-red-400/5 text-red-200" };
  return <div className={`flex items-center justify-between rounded-lg border px-3 py-2.5 ${styles[tone]}`}><span className="text-xs font-medium">{label}</span><Icon className="h-4 w-4" /></div>;
}

export function HealthPanel({ runtimeState, websocket }: { runtimeState: string; websocket: ConnectionStatus }) {
  const runtimeTone: HealthTone = runtimeState === "running" ? "healthy" : runtimeState === "starting" ? "warning" : "offline";
  const websocketTone: HealthTone = websocket === "connected" ? "healthy" : websocket === "connecting" ? "warning" : "offline";
  return <section className="rounded-xl border border-border bg-surface p-4 shadow-sm"><div className="flex items-center gap-2"><Activity className="h-4 w-4 text-primary" /><div><h2 className="text-sm font-semibold text-foreground">Health Matrix</h2><p className="mt-1 text-xs text-muted-foreground">Operational dependencies at a glance</p></div></div><div className="mt-4 grid gap-2 sm:grid-cols-2"><HealthItem label="Runtime" tone={runtimeTone} /><HealthItem label="WebSocket" tone={websocketTone} /><HealthItem label="Backend" tone={runtimeTone} /><HealthItem label="Execution System" tone={runtimeTone} /><HealthItem label="Agent Runtime" tone={runtimeTone} /></div></section>;
}
