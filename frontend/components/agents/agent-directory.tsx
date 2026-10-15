"use client";

import { useState } from "react";
import { Bot, CirclePlay, CircleStop, MoreHorizontal, Plus, Search, Settings2, Trash2, X } from "lucide-react";

import { AgentAvatar } from "@/components/agents/agent-avatar";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Input } from "@/components/ui/field";
import { Menu, type MenuEntry } from "@/components/ui/menu";
import { StatusBadge } from "@/components/ui/status-badge";
import { agentFilterCounts, canEditSettings, filterAgents, lifecycleActionsFor, type AgentFilter, type LifecycleAction } from "@/lib/agent-directory";
import { agentReadiness, modelLabel } from "@/lib/agent-experience";
import { cn } from "@/lib/utils";
import type { Agent, LLMModelOption } from "@/types/agents";

const SETUP_PROBLEMS = new Set(["needs-model", "model-unavailable", "provider-unconfigured"]);

export interface AgentDirectoryProps {
  agents: Agent[];
  loading: boolean;
  selectedId: string | null;
  models: LLMModelOption[] | null;
  pendingIds: ReadonlySet<string>;
  onSelect: (agentId: string) => void;
  onCreate: () => void;
  onConfigure: (agent: Agent) => void;
  onAction: (agent: Agent, action: LifecycleAction) => void;
}

/** "Your Agents": search, status filters and the list. Selecting an Agent opens its workspace. */
export function AgentDirectory({ agents, loading, selectedId, models, pendingIds, onSelect, onCreate, onConfigure, onAction }: AgentDirectoryProps) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<AgentFilter>("all");
  const filters = agentFilterCounts(agents);
  // A filter whose last Agent changed status falls back to "All" instead of an empty list.
  const activeFilter = filters.some((item) => item.value === filter) ? filter : "all";
  const visible = filterAgents(agents, query, activeFilter);
  const filtered = query.trim() !== "" || activeFilter !== "all";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-col gap-3 border-b border-border p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold tracking-tight text-foreground">Your Agents</h1>
            <p className="mt-0.5 text-xs leading-5 text-muted-foreground">Create Agents, chat with them and see what they do.</p>
          </div>
          <Button variant="primary" size="sm" icon={<Plus aria-hidden className="h-3.5 w-3.5" />} onClick={onCreate} className="shrink-0">Create Agent</Button>
        </div>
        {agents.length > 0 && (
          <>
            <div className="relative">
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by name, purpose or model" aria-label="Search Agents" className="pl-8 pr-8" />
              {query && (
                <button type="button" onClick={() => setQuery("")} aria-label="Clear search" className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground">
                  <X aria-hidden className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            {filters.length > 2 && (
              <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-1">
                {filters.map((item) => (
                  <button key={item.value} type="button" aria-pressed={activeFilter === item.value} onClick={() => setFilter(item.value)}
                    className={cn("inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors", activeFilter === item.value ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground")}>
                    {item.label}<span className="tabular-nums text-subtle">{item.count}</span>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="flex flex-col gap-2 p-2" aria-busy="true" aria-label="Loading Agents">
            {Array.from({ length: 4 }, (_, index) => <div key={index} className="flex gap-3 p-2"><Skeleton className="h-9 w-9" /><div className="flex-1 space-y-2"><Skeleton className="h-3.5 w-2/3" /><Skeleton className="h-3 w-1/2" /></div></div>)}
          </div>
        ) : agents.length === 0 ? (
          <EmptyState icon={Bot} title="No Agents yet" className="m-2 border-none"
            description="An Agent is an AI assistant with its own instructions, model, tools and memory. Create one to start chatting."
            action={<Button variant="primary" size="sm" icon={<Plus aria-hidden className="h-3.5 w-3.5" />} onClick={onCreate}>Create your first Agent</Button>} />
        ) : visible.length === 0 ? (
          <EmptyState icon={Search} title="No Agents match" className="m-2 border-none"
            description={query.trim() ? `Nothing matches “${query.trim()}”${activeFilter !== "all" ? " with this status" : ""}.` : "No Agents have this status."}
            action={<Button size="sm" onClick={() => { setQuery(""); setFilter("all"); }}>Clear search and filters</Button>} />
        ) : (
          <nav aria-label="Agents">
            <ul className="flex flex-col gap-0.5">
              {visible.map((agent) => (
                <AgentRow key={agent.id} agent={agent} selected={agent.id === selectedId} models={models} pending={pendingIds.has(agent.id)}
                  onSelect={() => onSelect(agent.id)} onConfigure={() => onConfigure(agent)} onAction={(action) => onAction(agent, action)} />
              ))}
            </ul>
            {filtered && <p className="px-3 py-2 text-[11px] text-muted-foreground" aria-live="polite">{visible.length} of {agents.length} Agents</p>}
          </nav>
        )}
      </div>
    </div>
  );
}

function AgentRow({ agent, selected, models, pending, onSelect, onConfigure, onAction }: {
  agent: Agent; selected: boolean; models: LLMModelOption[] | null; pending: boolean;
  onSelect: () => void; onConfigure: () => void; onAction: (action: LifecycleAction) => void;
}) {
  const readiness = agentReadiness(agent, models);
  const problem = SETUP_PROBLEMS.has(readiness.state) ? readiness.label : null;
  const actions = lifecycleActionsFor(agent.status);
  const items: MenuEntry[] = [
    { key: "open", label: "Open", icon: <Bot />, onSelect },
    { key: "settings", label: "Settings", icon: <Settings2 />, onSelect: onConfigure, disabled: !canEditSettings(agent.status) || pending },
  ];
  if (actions.length) items.push("separator");
  if (actions.includes("initialize")) items.push({ key: "initialize", label: "Finish setup", icon: <CirclePlay />, onSelect: () => onAction("initialize"), disabled: pending });
  if (actions.includes("stop")) items.push({ key: "stop", label: "Stop Agent", icon: <CircleStop />, onSelect: () => onAction("stop"), disabled: pending, description: "It can no longer chat" });
  if (actions.includes("delete")) items.push({ key: "delete", label: "Delete…", icon: <Trash2 />, onSelect: () => onAction("delete"), disabled: pending, danger: true });

  return (
    <li className="group relative">
      <button type="button" onClick={onSelect} aria-current={selected ? "page" : undefined}
        className={cn("flex w-full items-start gap-3 rounded-md px-2.5 py-2.5 pr-10 text-left transition-colors", selected ? "bg-white/[0.06]" : "hover:bg-white/[0.035]")}>
        {selected && <span aria-hidden className="absolute inset-y-2.5 left-0 w-0.5 rounded-full bg-accent" />}
        <AgentAvatar name={agent.name} />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="min-w-0 truncate text-sm font-medium text-foreground" title={agent.name}>{agent.name}</span>
          </span>
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">{agent.description || "No description"}</span>
          <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            <StatusBadge status={agent.status} />
            <span className="min-w-0 truncate text-[11px] text-subtle">{agent.llm_model ? modelLabel(agent.llm_model) : "No model"}</span>
          </span>
          {problem && <span className="mt-1 block text-[11px] text-warning">{problem}</span>}
        </span>
      </button>
      <div className="absolute right-1.5 top-2">
        <Menu triggerLabel={`Actions for ${agent.name}`} items={items} trigger={<MoreHorizontal aria-hidden className="h-4 w-4" />}
          triggerClassName={cn("inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.08] hover:text-foreground", !selected && "lg:opacity-0 lg:group-hover:opacity-100 lg:focus-visible:opacity-100 lg:aria-expanded:opacity-100")} />
      </div>
    </li>
  );
}
