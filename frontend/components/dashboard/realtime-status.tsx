"use client";

import { Radio } from "lucide-react";

import type { ConnectionStatus } from "@/types/realtime";

interface RealtimeStatusProps {
  connectionStatus: ConnectionStatus;
  runtimeState: string;
  lastHeartbeat: string | null;
}

const statusStyles: Record<ConnectionStatus, string> = {
  connected: "bg-emerald-400",
  connecting: "bg-amber-400",
  disconnected: "bg-red-400",
};

export function RealtimeStatus({
  connectionStatus,
  runtimeState,
  lastHeartbeat,
}: RealtimeStatusProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <span className={`h-2 w-2 rounded-full ${statusStyles[connectionStatus]}`} />
        {connectionStatus.charAt(0).toUpperCase() + connectionStatus.slice(1)}
      </span>
      <span className="flex items-center gap-1.5">
        <Radio className="h-3.5 w-3.5" /> Runtime: {runtimeState}
      </span>
      <span>
        Last heartbeat: {lastHeartbeat ? new Date(lastHeartbeat).toLocaleTimeString() : "Awaiting"}
      </span>
    </div>
  );
}
