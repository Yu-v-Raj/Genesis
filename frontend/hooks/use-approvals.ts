"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { RealtimeState } from "@/hooks/use-realtime";
import { ApprovalApiError, ApprovalService } from "@/services/approval.service";
import type { Approval, ApprovalActionResponse } from "@/types/approvals";

const message = (error: unknown) => (error instanceof ApprovalApiError ? error.message : "The Approval Gateway request could not be completed.");

export type ApprovalAction = "approve" | "reject" | "cancel" | "run";
export type ActionResult = { result: ApprovalActionResponse; error: null } | { result: null; error: string };

/**
 * Approval requests from the server, refreshed on every `approval.*` event (and on
 * execution/workflow events, which follow decisions). The server's record is the only
 * state: an action's result replaces the row, never an optimistic guess.
 */
export function useApprovals(realtime: RealtimeState) {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyIds, setBusyIds] = useState<ReadonlySet<string>>(new Set());
  const inFlight = useRef(new Set<string>());
  const event = realtime.latestEvent;
  const relevant = event !== null && /^(approval|execution|workflow)\./.test(event.event_type) ? event.id : null;

  const load = useCallback(async () => {
    try {
      setApprovals((await ApprovalService.list()).approvals);
      setError(null);
    } catch (caught) {
      setError(message(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);
  useEffect(() => { if (relevant) queueMicrotask(() => void load()); }, [relevant, load]);

  const act = useCallback(async (id: string, action: ApprovalAction): Promise<ActionResult> => {
    // A ref, not state: a double click must not send a second request before re-render.
    if (inFlight.current.has(id)) return { result: null, error: "This request is already being updated." };
    inFlight.current.add(id);
    setBusyIds(new Set(inFlight.current));
    try {
      const result = await ApprovalService[action](id);
      setApprovals((current) => current.map((item) => (item.approval_id === id ? result.approval : item)));
      return { result, error: null };
    } catch (caught) {
      void load();  // someone else may have decided it; show the stored state
      return { result: null, error: message(caught) };
    } finally {
      inFlight.current.delete(id);
      setBusyIds(new Set(inFlight.current));
    }
  }, [load]);

  return { approvals, loading, error, busyIds, act, reload: load };
}
