"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { Activity, Bot, BrainCircuit, Cpu, CornerDownLeft, LayoutGrid, PanelLeft, Plus, Search, Workflow, Wrench, X, type LucideIcon } from "lucide-react";

import { IconButton } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/disclosure";
import { buildCommands, filterCommands, moveActive, nextActiveId, type Command } from "@/lib/commands";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  "go:/": LayoutGrid, "go:/agents": Bot, "go:/memory": BrainCircuit, "go:/workflows": Workflow,
  "go:/monitoring": Activity, "go:/tools": Wrench, "go:/providers": Cpu,
  "action:create-agent": Plus, "action:create-workflow": Plus, "action:toggle-sidebar": PanelLeft,
};

/**
 * Jump to any page or start a supported flow from the keyboard. Searching is local; choosing
 * a command only navigates or changes a local preference — it never calls the server.
 * Rendered only while open, so every opening starts with an empty query.
 */
export function CommandPalette({ onClose, sidebarCollapsed, onToggleSidebar }: { onClose: () => void; sidebarCollapsed: boolean; onToggleSidebar: () => void }) {
  const router = useRouter();
  const ids = useId();
  const [query, setQuery] = useState("");
  const [chosenId, setChosenId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const commands = buildCommands(NAV_ITEMS, sidebarCollapsed);
  const results = filterCommands(commands, query);
  const activeId = nextActiveId(results, chosenId);
  const listId = `${ids}-list`;
  const optionId = (id: string) => `${ids}-${id.replace(/[^a-z0-9-]/gi, "-")}`;

  useEffect(() => {
    if (activeId) document.getElementById(optionId(activeId))?.scrollIntoView({ block: "nearest" });
    // optionId is derived from the stable useId value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  // Both clear buttons disappear once the query is empty, so keep focus in the search field.
  function clear() {
    setQuery("");
    inputRef.current?.focus();
  }

  function run(command: Command) {
    onClose();
    if (command.action === "toggle-sidebar") onToggleSidebar();
    else if (command.href) router.push(command.href);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setChosenId(moveActive(results, activeId, event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Home" && results.length) {
      event.preventDefault();
      setChosenId(results[0].id);
    } else if (event.key === "End" && results.length) {
      event.preventDefault();
      setChosenId(results[results.length - 1].id);
    } else if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      const command = results.find((item) => item.id === activeId);
      if (command) run(command);
    }
  }

  const groups = (["Go to", "Actions"] as const).map((group) => ({ group, items: results.filter((command) => command.group === group) })).filter(({ items }) => items.length);

  return (
    <Dialog open onClose={onClose} layout="palette" title="Command palette" description="Search pages and actions, then press Enter to open one.">
      <div className="flex items-center gap-2 border-b border-border px-3">
        <Search aria-hidden className="h-4 w-4 shrink-0 text-muted-foreground" />
        <input
          ref={inputRef}
          data-autofocus
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeId ? optionId(activeId) : undefined}
          aria-label="Search pages and actions"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search pages and actions…"
          autoComplete="off"
          spellCheck={false}
          className="h-12 min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-subtle"
        />
        {query && (
          <button type="button" onClick={clear} className="shrink-0 rounded px-1.5 py-1 text-xs text-muted-foreground hover:text-foreground">Clear</button>
        )}
        <IconButton label="Close command palette" onClick={onClose} className="-mr-1"><X aria-hidden className="h-4 w-4" /></IconButton>
      </div>

      <div id={listId} role="listbox" aria-label="Commands" className="min-h-0 flex-1 overflow-y-auto p-1.5">
        {groups.map(({ group, items }) => (
          <div key={group} role="group" aria-labelledby={`${ids}-${group.replace(" ", "")}`} className="py-1">
            <p id={`${ids}-${group.replace(" ", "")}`} className="px-2.5 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-wider text-subtle">{group}</p>
            {items.map((command) => {
              const active = command.id === activeId;
              const Icon = ICONS[command.id] ?? Search;
              return (
                <div
                  key={command.id}
                  id={optionId(command.id)}
                  role="option"
                  aria-selected={active}
                  onMouseMove={() => { if (!active) setChosenId(command.id); }}
                  onClick={() => run(command)}
                  className={cn("relative flex min-h-10 cursor-pointer items-center gap-3 rounded-md px-2.5 py-2 text-sm", active ? "bg-white/[0.07] text-foreground" : "text-muted-foreground")}
                >
                  {active && <span aria-hidden className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" />}
                  <Icon aria-hidden className={cn("h-4 w-4 shrink-0", active ? "text-accent" : "text-muted-foreground")} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-foreground">{command.label}</span>
                    {command.hint && <span className="block truncate text-[11px] text-muted-foreground">{command.hint}</span>}
                  </span>
                  {active && <CornerDownLeft aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
                </div>
              );
            })}
          </div>
        ))}
        {results.length === 0 && (
          <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
            <p className="text-sm text-foreground">No commands match “{query.trim()}”.</p>
            <button type="button" onClick={clear} className="text-xs text-accent hover:underline">Clear search</button>
          </div>
        )}
      </div>

      <p className="sr-only" aria-live="polite">{results.length === 0 ? "No results" : `${results.length} result${results.length === 1 ? "" : "s"}`}</p>
      <div aria-hidden className="hidden items-center gap-3 border-t border-border px-3 py-2 text-[11px] text-subtle sm:flex">
        <span className="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> move</span>
        <span className="flex items-center gap-1"><Kbd>↵</Kbd> open</span>
        <span className="flex items-center gap-1"><Kbd>esc</Kbd> close</span>
      </div>
    </Dialog>
  );
}
