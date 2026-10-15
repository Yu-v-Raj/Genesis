"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bot, BrainCircuit, Cpu, LayoutGrid, PanelLeftClose, PanelLeftOpen, Workflow, Wrench, type LucideIcon } from "lucide-react";
import { GenesisMark } from "@/components/brand/genesis-mark";
import { IconButton } from "@/components/ui/button";
import { NAVIGATION, isActivePath, type NavIconName } from "@/lib/navigation";
import { cn } from "@/lib/utils";

const ICONS: Record<NavIconName, LucideIcon> = {
  overview: LayoutGrid,
  agents: Bot,
  memory: BrainCircuit,
  workflows: Workflow,
  operations: Activity,
  tools: Wrench,
  providers: Cpu,
};

/*
 * Collapsed appearance comes from the `sidebar-collapsed:` CSS variant (see globals.css), which
 * applies only inside #app-sidebar and is correct from the first paint. The `collapsed` prop is
 * used only for non-visual details such as tooltips and the toggle's accessible name.
 */

/** The navigation list; shared by the desktop sidebar and the mobile drawer. */
export function SidebarNav({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-5 overflow-y-auto px-2 py-3">
      {NAVIGATION.map((group, index) => (
        <div key={group.label ?? index} role="group" aria-label={group.label ?? undefined}>
          {group.label && (
            <>
              <p aria-hidden className="mb-1.5 px-3 text-[11px] font-medium uppercase tracking-wider text-subtle sidebar-collapsed:hidden">{group.label}</p>
              <div aria-hidden className="mx-3 mb-2 hidden border-t border-border sidebar-collapsed:block" />
            </>
          )}
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const Icon = ICONS[item.icon];
              const active = isActivePath(item.href, pathname);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      "group relative flex h-9 items-center gap-3 rounded-md px-3 text-sm transition-colors duration-150 sidebar-collapsed:justify-center sidebar-collapsed:px-0",
                      active ? "bg-white/[0.06] text-foreground" : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground",
                    )}
                  >
                    {active && <span aria-hidden className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" />}
                    <Icon aria-hidden className={cn("h-4 w-4 shrink-0", active ? "text-accent" : "text-muted-foreground group-hover:text-foreground")} />
                    <span className="truncate sidebar-collapsed:sr-only">{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function Brand() {
  return (
    <Link href="/" aria-label="Genesis overview" className="flex min-w-0 items-center gap-2.5 rounded-md sidebar-collapsed:justify-center">
      <GenesisMark className="h-7 w-7 shrink-0" />
      <span className="min-w-0 leading-tight sidebar-collapsed:hidden">
        <span className="block text-sm font-semibold tracking-tight text-foreground">Genesis</span>
        <span className="block text-[11px] text-muted-foreground">Agent OS</span>
      </span>
    </Link>
  );
}

/**
 * Desktop sidebar (md and up). The width transition is enabled only after the user toggles,
 * so loading a page never animates, and the global reduced-motion rule shortens it to nothing.
 */
export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const [animate, setAnimate] = useState(false);
  return (
    <aside
      id="app-sidebar"
      aria-label="Sidebar"
      className={cn(
        "hidden h-full w-60 shrink-0 flex-col border-r border-border bg-surface md:flex sidebar-collapsed:w-[4.5rem]",
        animate && "transition-[width] duration-200 ease-standard",
      )}
    >
      <div className="flex h-14 shrink-0 items-center border-b border-border px-4 sidebar-collapsed:justify-center sidebar-collapsed:px-2">
        <Brand />
      </div>
      <SidebarNav collapsed={collapsed} />
      <div className="flex shrink-0 items-center justify-end border-t border-border p-2 sidebar-collapsed:justify-center">
        <IconButton label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} aria-controls="app-sidebar" onClick={() => { setAnimate(true); onToggle(); }}>
          <PanelLeftClose aria-hidden className="h-4 w-4 sidebar-collapsed:hidden" />
          <PanelLeftOpen aria-hidden className="hidden h-4 w-4 sidebar-collapsed:block" />
        </IconButton>
      </div>
    </aside>
  );
}
