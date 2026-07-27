export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export type RealtimeValue =
  | string
  | number
  | boolean
  | null
  | RealtimePayload
  | RealtimeValue[];

export interface RealtimePayload {
  [key: string]: RealtimeValue;
}

export interface RealtimeEvent {
  id: string;
  timestamp: string;
  event_type: string;
  source: string;
  payload: RealtimePayload;
}

export interface ConnectedMessage {
  type: "connected";
  timestamp: string;
}

export interface EventMessage {
  type: "event";
  event: RealtimeEvent;
}

export type RealtimeMessage = ConnectedMessage | EventMessage;
