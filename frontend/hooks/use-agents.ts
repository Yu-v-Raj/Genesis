"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AgentApiError, AgentService } from "@/services/agent.service";
import { EventHistoryService } from "@/services/event-history.service";
import { useRealtime } from "@/hooks/use-realtime";
import type { RealtimeEvent } from "@/types/realtime";
import type { Agent, AgentContext, CreateAgentInput } from "@/types/agents";

const AGENT_EVENT_TYPES = new Set([
  "agent.created",
  "agent.initialized",
  "agent.started",
  "agent.paused",
  "agent.resumed",
  "agent.completed",
  "agent.failed",
  "agent.stopped",
  "agent.deleted",
]);

function agentIdFromEvent(event: RealtimeEvent): string | null {
  const agentId = event.payload.agent_id;
  return typeof agentId === "string" ? agentId : null;
}

function isAgentEvent(event: RealtimeEvent): boolean {
  return AGENT_EVENT_TYPES.has(event.event_type) && agentIdFromEvent(event) !== null;
}

function upsertAgent(agents: Agent[], updatedAgent: Agent): Agent[] {
  const index = agents.findIndex((agent) => agent.id === updatedAgent.id);
  if (index === -1) return [updatedAgent, ...agents];
  return agents.map((agent) => (agent.id === updatedAgent.id ? updatedAgent : agent));
}

function appendEvent(events: RealtimeEvent[], event: RealtimeEvent): RealtimeEvent[] {
  if (!isAgentEvent(event) || events.some((existing) => existing.id === event.id)) return events;
  return [event, ...events].slice(0, 100);
}

function errorMessage(error: unknown): string {
  return error instanceof AgentApiError
    ? error.message
    : "The Agent Runtime request could not be completed.";
}

export interface AgentsState {
  agents: Agent[];
  events: RealtimeEvent[];
  contexts: Record<string, AgentContext | null | undefined>;
  loading: boolean;
  error: string | null;
  pendingAgentIds: ReadonlySet<string>;
  connectionStatus: ReturnType<typeof useRealtime>["connectionStatus"];
  latestAgentEvent: RealtimeEvent | null;
  createAgent: (input: CreateAgentInput) => Promise<boolean>;
  runLifecycleAction: (
    agentId: string,
    action: "initialize" | "start" | "pause" | "resume" | "stop" | "delete"
  ) => Promise<boolean>;
  loadContext: (agentId: string) => Promise<void>;
  retry: () => Promise<void>;
}

/** Coordinates Agent Runtime REST snapshots with its existing WebSocket event stream. */
export function useAgents(): AgentsState {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [events, setEvents] = useState<RealtimeEvent[]>([]);
  const [contexts, setContexts] = useState<Record<string, AgentContext | null | undefined>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingAgentIds, setPendingAgentIds] = useState<Set<string>>(new Set());
  const { connectionStatus, latestEvent } = useRealtime();
  const latestAgentEvent = latestEvent !== null && isAgentEvent(latestEvent) ? latestEvent : null;

  const refreshEvents = useCallback(async () => {
    try {
      const history = await EventHistoryService.recent();
      setEvents(history.events.filter(isAgentEvent));
    } catch {
      // Agent management remains usable when optional historical observability is unavailable.
    }
  }, []);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await AgentService.list();
      setAgents(result.agents);
      void refreshEvents();
    } catch (caughtError) {
      setError(errorMessage(caughtError));
    } finally {
      setLoading(false);
    }
  }, [refreshEvents]);

  useEffect(() => {
    queueMicrotask(() => void loadAgents());
  }, [loadAgents]);

  useEffect(() => {
    queueMicrotask(() => {
      if (latestAgentEvent === null) return;
      const agentId = agentIdFromEvent(latestAgentEvent);
      if (agentId === null) return;

      setEvents((current) => appendEvent(current, latestAgentEvent));
      if (latestAgentEvent.event_type === "agent.deleted") {
        setAgents((current) => current.filter((agent) => agent.id !== agentId));
        setContexts((current) => {
          const remaining = { ...current };
          delete remaining[agentId];
          return remaining;
        });
        return;
      }

      void AgentService.get(agentId)
        .then((agent) => setAgents((current) => upsertAgent(current, agent)))
        .catch(() => undefined);
    });
  }, [latestAgentEvent]);

  const createAgent = useCallback(
    async (input: CreateAgentInput): Promise<boolean> => {
      setError(null);
      try {
        const agent = await AgentService.create(input);
        setAgents((current) => upsertAgent(current, agent));
        void refreshEvents();
        return true;
      } catch (caughtError) {
        setError(errorMessage(caughtError));
        return false;
      }
    },
    [refreshEvents]
  );

  const runLifecycleAction = useCallback(
    async (
      agentId: string,
      action: "initialize" | "start" | "pause" | "resume" | "stop" | "delete"
    ): Promise<boolean> => {
      setPendingAgentIds((current) => new Set(current).add(agentId));
      setError(null);
      try {
        const agent =
          action === "delete"
            ? await AgentService.delete(agentId)
            : await AgentService[action](agentId);
        if (action === "delete") {
          setAgents((current) => current.filter((existing) => existing.id !== agent.id));
          setContexts((current) => {
            const remaining = { ...current };
            delete remaining[agentId];
            return remaining;
          });
        } else {
          setAgents((current) => upsertAgent(current, agent));
        }
        void refreshEvents();
        return true;
      } catch (caughtError) {
        setError(errorMessage(caughtError));
        return false;
      } finally {
        setPendingAgentIds((current) => {
          const next = new Set(current);
          next.delete(agentId);
          return next;
        });
      }
    },
    [refreshEvents]
  );

  const loadContext = useCallback(async (agentId: string): Promise<void> => {
    try {
      const context = await AgentService.getContext(agentId);
      setContexts((current) => ({ ...current, [agentId]: context }));
    } catch (caughtError) {
      if (caughtError instanceof AgentApiError && caughtError.status === 404) {
        setContexts((current) => ({ ...current, [agentId]: null }));
        return;
      }
      setError(errorMessage(caughtError));
    }
  }, []);

  return {
    agents,
    events,
    contexts,
    loading,
    error,
    pendingAgentIds: useMemo(() => pendingAgentIds, [pendingAgentIds]),
    connectionStatus,
    latestAgentEvent,
    createAgent,
    runLifecycleAction,
    loadContext,
    retry: loadAgents,
  };
}
