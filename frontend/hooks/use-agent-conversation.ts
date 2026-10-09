"use client";

import { useCallback, useEffect, useState } from "react";
import { AgentApiError, AgentService } from "@/services/agent.service";
import type { AgentChatResponse, AgentSession, SessionMessage } from "@/types/agents";

export function useAgentConversation(agentId: string | null) {
  const [session, setSession] = useState<AgentSession | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!agentId) return setSession(null);
    try { setError(null); setSession(await AgentService.getSession(agentId)); }
    catch (cause) { setError(cause instanceof AgentApiError ? cause.message : "Unable to load this conversation."); }
  }, [agentId]);
  useEffect(() => { queueMicrotask(() => void load()); }, [load]);
  const send = useCallback(async (message: string): Promise<AgentChatResponse | null> => {
    if (!agentId || !message.trim()) return null;
    setPending(true); setError(null);
    try {
      const response = await AgentService.chat(agentId, message.trim());
      await load();
      return response;
    } catch (cause) {
      setError(cause instanceof AgentApiError && cause.status === 409 ? "This Agent is busy. Try again shortly." : "Unable to generate a response. Please try again.");
      return null;
    } finally { setPending(false); }
  }, [agentId, load]);
  return { messages: session?.messages ?? ([] as SessionMessage[]), pending, error, send, reload: load };
}
