"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AgentApiError, AgentService } from "@/services/agent.service";
import { describeChatError, type ChatProblem } from "@/lib/agent-experience";
import type { Agent, AgentChatResponse, AgentSession, SessionMessage } from "@/types/agents";

/**
 * Conversation state for one Agent. The session endpoint is the source of truth; while a
 * request is in flight the user's message is shown optimistically and removed if it fails
 * (the backend commits nothing for failed turns).
 */
export function useAgentConversation(agentId: string | null, onAgentUpdated?: (agent: Agent) => void) {
  const [session, setSession] = useState<AgentSession | null>(null);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [problem, setProblem] = useState<ChatProblem | null>(null);
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    if (!agentId) return setSession(null);
    try {
      setLoadError(null);
      setSession(await AgentService.getSession(agentId));
    } catch (cause) {
      setLoadError(cause instanceof AgentApiError ? cause.message : "Unable to load this conversation.");
    }
  }, [agentId]);

  useEffect(() => {
    queueMicrotask(() => {
      setProblem(null);
      void load();
    });
  }, [load]);

  const send = useCallback(async (message: string): Promise<AgentChatResponse | null> => {
    const text = message.trim();
    // A ref (not state) guards against double submission before React re-renders.
    if (!agentId || !text || inFlight.current) return null;
    inFlight.current = true;
    setPendingMessage(text);
    setProblem(null);
    try {
      const response = await AgentService.chat(agentId, text);
      onAgentUpdated?.(response.agent);
      await load();
      return response;
    } catch (cause) {
      const status = cause instanceof AgentApiError ? cause.status : undefined;
      setProblem(describeChatError(status, cause instanceof Error ? cause.message : String(cause)));
      if (status === 409 || status === 503) {
        void AgentService.get(agentId).then((agent) => onAgentUpdated?.(agent)).catch(() => undefined);
      }
      return null;
    } finally {
      inFlight.current = false;
      setPendingMessage(null);
    }
  }, [agentId, load, onAgentUpdated]);

  return {
    messages: session?.messages ?? ([] as SessionMessage[]),
    pendingMessage,
    pending: pendingMessage !== null,
    loadError,
    problem,
    dismissProblem: () => setProblem(null),
    send,
    reload: load,
  };
}
