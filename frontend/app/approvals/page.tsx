"use client";

import { Suspense } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { History, ShieldCheck } from "lucide-react";

import { ApprovalDetail } from "@/components/approvals/approval-detail";
import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, tabPanelProps, type TabItem } from "@/components/ui/tabs";
import { useApprovals } from "@/hooks/use-approvals";
import { useNow } from "@/hooks/use-now";
import { useRealtime } from "@/hooks/use-realtime";
import { expiryText, requesterText, splitApprovals } from "@/lib/approvals";
import { relativeTime } from "@/lib/operations";
import { toolLabel } from "@/lib/tools";
import { cn } from "@/lib/utils";
import type { Approval } from "@/types/approvals";

type Tab = "pending" | "history";
const TAB_PREFIX = "approvals";

export default function ApprovalsPage() {
  // The open request and tab live in the URL (?approval=…&tab=history); useSearchParams needs Suspense.
  return (
    <Suspense fallback={<div className="mx-auto max-w-6xl space-y-4 px-4 py-6 sm:px-6 sm:py-8" aria-busy="true"><Skeleton className="h-8 w-40" /><Skeleton className="h-80 w-full" /></div>}>
      <Approvals />
    </Suspense>
  );
}

function Approvals() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const realtime = useRealtime();
  const state = useApprovals(realtime);
  const now = useNow();

  const { pending, history } = splitApprovals(state.approvals);
  const selectedId = params.get("approval");
  const selected = state.approvals.find((item) => item.approval_id === selectedId) ?? null;
  const tab: Tab = params.get("tab") === "history" || (selected !== null && selected.state !== "pending") ? "history" : "pending";
  const rows = tab === "pending" ? pending : history;

  function go(next: { approval?: string | null; tab?: Tab }, mode: "push" | "replace" = "replace") {
    const search = new URLSearchParams();
    const nextTab = next.tab ?? tab;
    const approval = next.approval !== undefined ? next.approval : selectedId;
    if (nextTab === "history") search.set("tab", "history");
    if (approval) search.set("approval", approval);
    const query = search.toString();
    router[mode](query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  const tabs: TabItem<Tab>[] = [
    { value: "pending", label: "Needs decision", badge: state.loading && state.approvals.length === 0 ? undefined : pending.length },
    { value: "history", label: "History", badge: state.loading && state.approvals.length === 0 ? undefined : history.length },
  ];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8">
      <RealtimeNotifications events={realtime.latestEvent ? [realtime.latestEvent] : []} />
      <PageHeader
        title="Approvals"
        description="Tool calls that can affect things outside Genesis wait here for your decision. Approving authorizes one exact call, once."
      />
      <p className="-mt-2 text-xs leading-5 text-muted-foreground">
        Decisions are recorded as made on this machine; Genesis has no accounts, so it doesn&apos;t identify who decided. Other programs running on this computer can also reach its local API.
      </p>

      {state.error && state.approvals.length === 0 ? (
        <Alert tone="danger" action={<Button size="sm" onClick={() => void state.reload()}>Try again</Button>}>
          <p className="font-medium">Approval requests couldn&apos;t be loaded.</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{state.error}</p>
        </Alert>
      ) : (
        <div>
          {state.error && <Alert tone="warning" className="mb-3" action={<Button size="sm" onClick={() => void state.reload()}>Refresh</Button>}>Couldn&apos;t refresh: {state.error}</Alert>}
          <Tabs idPrefix={TAB_PREFIX} label="Approval views" items={tabs} value={tab} onChange={(value) => go({ tab: value, approval: null })} />
          <div {...tabPanelProps(TAB_PREFIX, tab)} className="pt-5 focus:outline-none">
            {state.loading && state.approvals.length === 0 ? (
              <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading approval requests">{Array.from({ length: 3 }, (_, index) => <Skeleton key={index} className="h-16 w-full" />)}</div>
            ) : rows.length === 0 && !selected ? (
              tab === "pending" ? (
                <EmptyState icon={ShieldCheck} title="Nothing needs your decision" description="When an Agent, a workflow step or a test wants to run a tool that can affect things outside Genesis, the request appears here." />
              ) : (
                <EmptyState icon={History} title="No decided requests yet" description="Approved, rejected, expired, cancelled and used requests are kept here." />
              )
            ) : (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
                <ul aria-label={tab === "pending" ? "Requests that need a decision" : "Decided requests"} className={cn("min-w-0 self-start divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface", selected && "hidden lg:block")}>
                  {rows.map((item) => <ApprovalRow key={item.approval_id} approval={item} now={now} selected={item.approval_id === selectedId} onSelect={() => go({ approval: item.approval_id }, "push")} />)}
                </ul>
                <section aria-label="Approval request" className={cn("min-w-0 rounded-lg border border-border bg-surface p-4 sm:p-5", !selected && "hidden lg:block")}>
                  {selected ? (
                    <ApprovalDetail key={selected.approval_id} approval={selected} now={now} busy={state.busyIds.has(selected.approval_id)}
                      onAct={(action) => state.act(selected.approval_id, action)} onBack={() => go({ approval: null })} />
                  ) : selectedId ? (
                    <EmptyState icon={ShieldCheck} title="Request not found" description="It may be older than the requests listed here." action={<Button size="sm" onClick={() => go({ approval: null })}>Back to the list</Button>} />
                  ) : (
                    <div className="flex min-h-48 flex-col items-center justify-center text-center">
                      <ShieldCheck aria-hidden className="h-5 w-5 text-muted-foreground" />
                      <p className="mt-2 text-sm text-foreground">Select a request to review it</p>
                      <p className="mt-1 max-w-xs text-xs text-muted-foreground">You&apos;ll see the exact call, who asked for it, and what approving or rejecting will do.</p>
                    </div>
                  )}
                </section>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ApprovalRow({ approval, now, selected, onSelect }: { approval: Approval; now: Date; selected: boolean; onSelect: () => void }) {
  const pending = approval.state === "pending";
  return (
    <li>
      <button type="button" onClick={onSelect} aria-current={selected ? "true" : undefined}
        className={cn("relative flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.025]", selected && "bg-white/[0.05]")}>
        {selected && <span aria-hidden className="absolute inset-y-2.5 left-0 w-0.5 rounded-full bg-accent" />}
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-foreground">{toolLabel(approval.tool_name)}</span>
            <StatusBadge status={approval.state} />
          </span>
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">{requesterText(approval)}</span>
          <span className="mt-1 block text-[11px] text-subtle">
            {pending ? expiryText(approval.expires_at, now) : `Requested ${relativeTime(approval.created_at, now)}`}
          </span>
        </span>
      </button>
    </li>
  );
}
