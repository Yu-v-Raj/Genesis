"use client";

import { useCallback, useEffect, useState } from "react";
import { WorkflowService } from "@/services/workflow.service";

export interface WorkflowSummary {
  total: number;
  running: number;
  failed: number;
}

/** Lightweight REST-only workflow count for dashboards that already own realtime elsewhere. */
export function useWorkflowSummary(): WorkflowSummary | null {
  const [summary, setSummary] = useState<WorkflowSummary | null>(null);
  const load = useCallback(async () => {
    try {
      const { workflows } = await WorkflowService.list();
      setSummary({ total: workflows.length, running: workflows.filter((workflow) => workflow.status === "running").length, failed: workflows.filter((workflow) => workflow.status === "failed").length });
    } catch {
      // The home dashboard remains available when the optional workflow API is offline.
    }
  }, []);
  useEffect(() => { queueMicrotask(() => void load()); }, [load]);
  return summary;
}
