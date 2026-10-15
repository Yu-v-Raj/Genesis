"use client";

import { useCallback, useEffect, useState } from "react";

import type { RealtimeState } from "@/hooks/use-realtime";
import { AgentService } from "@/services/agent.service";
import { EventHistoryService } from "@/services/event-history.service";
import { LlmApiError, LlmService } from "@/services/llm.service";
import type { Agent, LLMModelOption } from "@/types/agents";
import type { RealtimeEvent } from "@/types/realtime";

const LLM_OUTCOMES = new Set(["llm.completed", "llm.failed"]);

export interface ProvidersData {
  providers: string[];
  models: LLMModelOption[];
  agents: Agent[];
  /** Retained model-call events (newest first), for evidence of real outcomes. */
  events: RealtimeEvent[];
}

/**
 * Everything the Providers page shows, from existing endpoints only. Credentials never
 * reach the browser: the server reports just whether each model is configured.
 */
export function useProviders(realtime: RealtimeState) {
  const [data, setData] = useState<ProvidersData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventsError, setEventsError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [providers, models, agents, events] = await Promise.all([
        LlmService.providers(),
        LlmService.models(),
        AgentService.list(),
        // Evidence is optional: the page still works without it.
        EventHistoryService.recent(1000).then((history) => history.events).catch(() => null),
      ]);
      setEventsError(events === null);
      setData({ providers: providers.providers, models: models.models, agents: agents.agents, events: (events ?? []).filter((event) => LLM_OUTCOMES.has(event.event_type)) });
    } catch (cause) {
      setError(cause instanceof LlmApiError || cause instanceof Error ? cause.message : "Provider information couldn't be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  // New model outcomes (from chats, other tabs or a test here) arrive live.
  useEffect(() => {
    const event = realtime.latestEvent;
    if (!event || !LLM_OUTCOMES.has(event.event_type)) return;
    queueMicrotask(() => setData((current) => current && !current.events.some((existing) => existing.id === event.id) ? { ...current, events: [event, ...current.events] } : current));
  }, [realtime.latestEvent]);

  return { data, loading, error, eventsError, reload: load };
}
