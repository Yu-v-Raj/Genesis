"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AgentApiError, AgentService } from "@/services/agent.service";
import { ExecutionApiError, ExecutionService } from "@/services/execution.service";
import { describeChatError, type ChatProblem } from "@/lib/agent-experience";
import { isActive, unfinishedChats } from "@/lib/durable-work";
import type { Execution } from "@/types/executions";
import type { Agent, AgentChatResponse, AgentSession, AgentSessionSummary, SessionMessage } from "@/types/agents";

/**
 * Conversation state for one Agent. Sessions are stored by the backend, so the open
 * session's history survives refreshes and restarts. With no explicit choice the Agent's
 * active (most recently used) session is shown. While a request is in flight the user's
 * message is shown optimistically; failed turns are never stored by the backend.
 *
 * `initialSessionId` (for example from the URL) is opened when the Agent is first shown;
 * if it doesn't exist or belongs to another Agent, the Agent's active session is used.
 */
export function useAgentConversation(agentId: string | null, onAgentUpdated?: (agent: Agent) => void, initialSessionId: string | null = null) {
  const [session, setSession] = useState<AgentSession | null>(null);
  const [sessions, setSessions] = useState<AgentSessionSummary[]>([]);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [problem, setProblem] = useState<ChatProblem | null>(null);
  const [switching, setSwitching] = useState(false);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const inFlight = useRef(false);
  const initialSession = useRef(initialSessionId);
  const sessionId = session?.id ?? null;

  useEffect(() => {
    initialSession.current = initialSessionId;
  }, [initialSessionId]);

  const refreshExecutions = useCallback(async () => {
    if (!agentId) return;
    try {
      setExecutions((await ExecutionService.listForAgent(agentId)).executions);
    } catch {
      // Unfinished-message hints are optional; the conversation still works.
    }
  }, [agentId]);

  const refreshSessions = useCallback(async () => {
    if (!agentId) return;
    try {
      setSessions((await AgentService.listSessions(agentId)).sessions);
    } catch {
      // The open conversation still works; the picker just stays stale.
    }
  }, [agentId]);

  const open = useCallback(async (sessionId: string | null, fallbackToActive = false) => {
    if (!agentId) {
      setSession(null);
      setSessions([]);
      return;
    }
    setLoading(true);
    try {
      setLoadError(null);
      let loaded: AgentSession;
      try {
        loaded = sessionId ? await AgentService.getSessionById(agentId, sessionId) : await AgentService.getSession(agentId);
      } catch (cause) {
        const missing = cause instanceof AgentApiError && (cause.status === 404 || cause.status === 422);
        if (!(fallbackToActive && sessionId && missing)) throw cause;
        loaded = await AgentService.getSession(agentId);
      }
      setSession(loaded);
      void refreshSessions();
      void refreshExecutions();
    } catch (cause) {
      setLoadError(cause instanceof AgentApiError ? cause.message : "Unable to load this conversation.");
    } finally {
      setLoading(false);
    }
  }, [agentId, refreshSessions, refreshExecutions]);

  useEffect(() => {
    queueMicrotask(() => {
      setProblem(null);
      setSession(null);
      setExecutions([]);
      void open(initialSession.current, true);
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
      void refreshExecutions();
      return null;
    } finally {
      inFlight.current = false;
      setPendingMessage(null);
    }
  }, [agentId, onAgentUpdated, open, sessionId, refreshExecutions]);

  /** Retry an unfinished message through the Execution Runtime, then follow it to the end. */
  const retryUnfinished = useCallback(async (executionId: string, acknowledgeSideEffects: boolean): Promise<string | null> => {
    try {
      let attempt = await ExecutionService.retry(executionId, acknowledgeSideEffects);
      await refreshExecutions();
      for (let waited = 0; isActive(attempt.status) && waited < 120_000; waited += 500) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        attempt = await ExecutionService.get(attempt.execution_id);
      }
      await open(sessionId);
      return attempt.status === "completed" ? null : attempt.error ?? `The retry ended as ${attempt.status}.`;
    } catch (cause) {
      return cause instanceof ExecutionApiError ? cause.message : "The retry could not be started.";
    }
  }, [open, refreshExecutions, sessionId]);

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
    /** The Agent the loaded session belongs to; callers ignore data for any other Agent. */
    sessionAgentId: session?.agent_id ?? null,
    messages: session?.messages ?? ([] as SessionMessage[]),
    /** This Agent's durable executions (newest first), for per-turn outcomes. */
    executions,
    refreshExecutions,
    pendingMessage,
    pending: pendingMessage !== null,
    loading,
    switching,
    loadError,
    problem,
    dismissProblem: () => setProblem(null),
    send,
    unfinished: unfinishedChats(executions, sessionId),
    retryUnfinished,
    startNewConversation,
    openSession,
    reload: () => open(sessionId),
  };
}
