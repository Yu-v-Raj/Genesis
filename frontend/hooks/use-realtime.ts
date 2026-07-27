"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { RealtimeService } from "@/services/realtime.service";
import type { ConnectionStatus, RealtimeEvent } from "@/types/realtime";

export interface RealtimeState {
  connectionStatus: ConnectionStatus;
  latestEvent: RealtimeEvent | null;
  connect: () => void;
  disconnect: () => void;
  reconnect: () => void;
}

/** Connect a React client to the centralized Genesis real-time event stream. */
export function useRealtime(): RealtimeState {
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("connecting");
  const [latestEvent, setLatestEvent] = useState<RealtimeEvent | null>(null);
  const serviceRef = useRef<RealtimeService | null>(null);

  useEffect(() => {
    const service = new RealtimeService({
      onConnectionStatusChange: setConnectionStatus,
      onEvent: setLatestEvent,
    });
    serviceRef.current = service;
    service.connect();

    return () => {
      service.disconnect();
      serviceRef.current = null;
    };
  }, []);

  const connect = useCallback(() => serviceRef.current?.connect(), []);
  const disconnect = useCallback(() => serviceRef.current?.disconnect(), []);
  const reconnect = useCallback(() => serviceRef.current?.reconnect(), []);

  return { connectionStatus, latestEvent, connect, disconnect, reconnect };
}
