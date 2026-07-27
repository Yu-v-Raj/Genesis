import type {
  ConnectionStatus,
  EventMessage,
  RealtimeEvent,
  RealtimeMessage,
  RealtimePayload,
  RealtimeValue,
} from "@/types/realtime";

const REALTIME_URL =
  process.env.NEXT_PUBLIC_REALTIME_URL ?? "ws://127.0.0.1:8000/ws/events";
const MAX_RECONNECT_DELAY_MS = 30_000;

interface RealtimeServiceOptions {
  onConnectionStatusChange: (status: ConnectionStatus) => void;
  onEvent: (event: RealtimeEvent) => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRealtimeValue(value: unknown): value is RealtimeValue {
  if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return true;
  }
  if (Array.isArray(value)) {
    return value.every(isRealtimeValue);
  }
  return isRecord(value) && Object.values(value).every(isRealtimeValue);
}

function isRealtimePayload(value: unknown): value is RealtimePayload {
  return isRecord(value) && Object.values(value).every(isRealtimeValue);
}

function isRealtimeEvent(value: unknown): value is RealtimeEvent {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.timestamp === "string" &&
    typeof value.event_type === "string" &&
    typeof value.source === "string" &&
    isRealtimePayload(value.payload)
  );
}

function parseMessage(data: string): RealtimeMessage | null {
  try {
    const message: unknown = JSON.parse(data);
    if (!isRecord(message) || typeof message.type !== "string") {
      return null;
    }
    if (message.type === "connected" && typeof message.timestamp === "string") {
      return { type: "connected", timestamp: message.timestamp };
    }
    if (message.type === "event" && isRealtimeEvent(message.event)) {
      const eventMessage: EventMessage = { type: "event", event: message.event };
      return eventMessage;
    }
    return null;
  } catch {
    return null;
  }
}

/** Centralized browser WebSocket client for the Genesis event stream. */
export class RealtimeService {
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private manuallyDisconnected = false;

  constructor(private readonly options: RealtimeServiceOptions) {}

  connect(): void {
    this.manuallyDisconnected = false;
    if (
      this.socket?.readyState === WebSocket.CONNECTING ||
      this.socket?.readyState === WebSocket.OPEN
    ) {
      return;
    }

    this.clearReconnectTimer();
    this.options.onConnectionStatusChange("connecting");
    const socket = new WebSocket(REALTIME_URL);
    this.socket = socket;

    socket.onopen = () => {
      if (this.socket !== socket) return;
      this.reconnectAttempts = 0;
      this.options.onConnectionStatusChange("connected");
    };
    socket.onmessage = (message) => {
      const parsed = typeof message.data === "string" ? parseMessage(message.data) : null;
      if (parsed?.type === "event") {
        this.options.onEvent(parsed.event);
      }
    };
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.options.onConnectionStatusChange("disconnected");
      if (!this.manuallyDisconnected) {
        this.scheduleReconnect();
      }
    };
    socket.onerror = () => socket.close();
  }

  disconnect(): void {
    this.manuallyDisconnected = true;
    this.clearReconnectTimer();
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    this.options.onConnectionStatusChange("disconnected");
  }

  reconnect(): void {
    // Replace the current connection without creating parallel sockets.
    this.disconnect();
    this.connect();
  }

  private scheduleReconnect(): void {
    const delay = Math.min(1_000 * 2 ** this.reconnectAttempts, MAX_RECONNECT_DELAY_MS);
    this.reconnectAttempts += 1;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
