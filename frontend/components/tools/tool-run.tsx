"use client";

import Link from "next/link";
import { ArrowUpRight, ChevronRight } from "lucide-react";

import { JsonView } from "@/components/ui/disclosure";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatDuration, operationsQuery, relativeTime } from "@/lib/operations";
import { toolLabel } from "@/lib/tools";
import { cn } from "@/lib/utils";
import type { ToolTask } from "@/types/tools";

/**
 * One recorded tool run. Output is untrusted data: shown as escaped JSON/text, collapsed
 * until asked for. Runs made by an Agent link to their execution in Operations.
 */
export function ToolRunRow({ task, now, showTool = false, links = true }: { task: ToolTask; now: Date; showTool?: boolean; links?: boolean }) {
  const status = task.result?.status ?? task.status;
  const at = task.finished_at ?? task.started_at ?? task.created_at;
  const shownArguments = task.arguments && Object.keys(task.arguments).length > 0 ? task.arguments : null;
  const approvalId = typeof task.metadata.approval_id === "string" ? task.metadata.approval_id : null;
  const interrupted = task.result?.metadata?.interrupted === true;
  const hasDetail = Boolean((task.result && (task.result.output !== null || task.result.error)) || shownArguments || approvalId);
  // Who made the call: an Agent's run, a workflow step (recorded in metadata), or an operator test.
  const workflowRun = typeof task.metadata.workflow_id === "string" ? task.metadata.workflow_id : null;
  const origin = task.execution_id ? "Called by an Agent" : workflowRun ? "Workflow step" : "Test run";
  return (
    <li>
      <details className="group/run">
        <summary className={cn("flex list-none items-center gap-3 px-4 py-2.5 text-xs [&::-webkit-details-marker]:hidden", hasDetail ? "cursor-pointer hover:bg-white/[0.025]" : "cursor-default")}>
          <span className="min-w-0 flex-1">
            {showTool && <span className="mr-2 font-medium text-foreground">{toolLabel(task.tool_name)}</span>}
            <span className="text-muted-foreground">{origin}</span>
            {interrupted && <span className="ml-2 text-warning">outcome unknown</span>}
          </span>
          <span className="hidden shrink-0 text-[11px] text-subtle sm:inline">{formatDuration(task.result?.duration)}</span>
          <time dateTime={at ?? undefined} title={at ? new Date(at).toLocaleString() : undefined} className="shrink-0 text-[11px] text-subtle">{relativeTime(at, now)}</time>
          <StatusBadge status={status} className="shrink-0" />
          {hasDetail && <ChevronRight aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open/run:rotate-90" />}
        </summary>
        {hasDetail && (
          <div className="flex flex-col gap-2 px-4 pb-3">
            {task.result?.error && <p className="break-words text-xs text-danger">{task.result.error}</p>}
            {shownArguments && <div><p className="mb-1 text-[11px] text-muted-foreground">Arguments (secret-looking values hidden)</p><JsonView value={shownArguments} className="max-h-32" /></div>}
            {task.result && task.result.output !== null && <div><p className="mb-1 text-[11px] text-muted-foreground">Output</p><JsonView value={task.result.output} className="max-h-48" /></div>}
            {approvalId && (
              <Link href={`/approvals?approval=${encodeURIComponent(approvalId)}`} className="inline-flex w-fit items-center gap-0.5 text-[11px] text-muted-foreground hover:text-foreground">
                Ran with an operator approval — open it<ArrowUpRight aria-hidden className="h-3 w-3" />
              </Link>
            )}
            {links && workflowRun && (
              <Link href={`/workflows?tab=runs&run=${encodeURIComponent(workflowRun)}`} className="inline-flex w-fit items-center gap-0.5 text-[11px] text-muted-foreground hover:text-foreground">
                Open the workflow run<ArrowUpRight aria-hidden className="h-3 w-3" />
              </Link>
            )}
            {links && task.execution_id && (
              <Link href={`/monitoring${operationsQuery({ execution: task.execution_id })}`} className="inline-flex w-fit items-center gap-0.5 text-[11px] text-muted-foreground hover:text-foreground">
                Open the Agent run in Operations<ArrowUpRight aria-hidden className="h-3 w-3" />
              </Link>
            )}
          </div>
        )}
      </details>
    </li>
  );
}
