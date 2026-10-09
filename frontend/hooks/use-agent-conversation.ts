"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AgentApiError, AgentService } from "@/services/agent.service";
import { describeChatError, type ChatProblem } from "@/lib/agent-experience";
import type { Agent, AgentChatResponse, AgentSession, AgentSessionSummary, SessionMessage } from "@/types/agents";

/**
 * Conversation state for one Agent. Sessions are stored by the backend, so the open
 * session's history survives refreshes and restarts. With no explicit choice the Agent's
 * active (most recently used) session is shown. While a request is in flight the user's
 * message is shown optimistically; failed turns are never stored by the backend.
 */
export function useAgentConversation(agentId: string | null, onAgentUpdated?: (agent: Agent) => void) {
  const [session, setSession] = useState<AgentSession | null>(null);
  const [sessions, setSessions] = useState<AgentSessionSummary[]>([]);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [problem, setProblem] = useState<ChatProblem | null>(null);
  const [switching, setSwitching] = useState(false);
  const inFlight = useRef(false);
  const sessionId = session?.id ?? null;

  const refreshSessions = useCallback(async () => {
    if (!agentId) return;
    try {
      setSessions((await AgentService.listSessions(agentId)).sessions);
    } catch {
      // The open conversation still works; the picker just stays stale.
    }
  }, [agentId]);

  const open = useCallback(async (sessionId: string | null) => {
    if (!agentId) {
      setSession(null);
      setSessions([]);
      return;
    }
    setLoading(true);
    try {
      setLoadError(null);
      setSession(sessionId ? await AgentService.getSessionById(agentId, sessionId) : await AgentService.getSession(agentId));
      void refreshSessions();
    } catch (cause) {
      setLoadError(cause instanceof AgentApiError ? cause.message : "Unable to load this conversation.");
    } finally {
      setLoading(false);
    }
  }, [agentId, refreshSessions]);

  useEffect(() => {
    queueMicrotask(() => {
      setProblem(null);
      setSession(null);
      void open(null);
    });
  }, [open]);

  const send = useCallback(async (message: string): Promise<AgentChatResponse | null> => {
    const text = message.trim();
    // A ref (not state) guards against double submission before React re-renders.
    if (!agentId || !text || inFlight.current) return null;
    inFlight.current = true;
    setPendingMessage(text);
    setProblem(null);
    try {
      const response = await AgentService.chat(agentId, text, sessionId);
      onAgentUpdated?.(response.agent);
      await open(response.session_id ?? sessionId);
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
  }, [agentId, onAgentUpdated, open, sessionId]);

  const startNewConversation = useCallback(async () => {
    if (!agentId || inFlight.current) return;
    setSwitching(true);
    setProblem(null);
    try {
      const created = await AgentService.startSession(agentId);
      setSession(created);
      void refreshSessions();
    } catch (cause) {
      const status = cause instanceof AgentApiError ? cause.status : undefined;
      setProblem(describeChatError(status, cause instanceof Error ? cause.message : String(cause)));
    } finally {
      setSwitching(false);
    }
  }, [agentId, refreshSessions]);

  const openSession = useCallback(async (targetId: string) => {
    if (inFlight.current || targetId === sessionId) return;
    setProblem(null);
    await open(targetId);
  }, [open, sessionId]);

  return {
    sessionId,
    sessions,
    messages: session?.messages ?? ([] as SessionMessage[]),
    pendingMessage,
    pending: pendingMessage !== null,
    loading,
    switching,
    loadError,
    problem,
    dismissProblem: () => setProblem(null),
    send,
    startNewConversation,
    openSession,
    reload: () => open(sessionId),
  };
}
