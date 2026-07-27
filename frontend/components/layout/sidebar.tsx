"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Cpu,
  Wrench,
  Puzzle,
  BrainCircuit,
  Workflow,
  Bot,
  Activity,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  icon: React.ElementType;
  active?: boolean;
}

const navItems: NavItem[] = [
  { label: "Dashboard", icon: LayoutDashboard, active: true },
  { label: "Core", icon: Cpu },
  { label: "Tools", icon: Wrench },
  { label: "Plugins", icon: Puzzle },
  { label: "Memory", icon: BrainCircuit },
  { label: "Workflows", icon: Workflow },
  { label: "Agents", icon: Bot },
  { label: "Monitoring", icon: Activity },
  { label: "Settings", icon: Settings },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <motion.aside
      animate={{ width: collapsed ? 72 : 240 }}
      transition={{ duration: 0.2, ease: "easeInOut" }}
      className="relative flex h-screen shrink-0 flex-col border-r border-border bg-surface"
    >
      <div className="flex h-16 items-center justify-between px-4">
        {!collapsed && (
          <span className="text-sm font-semibold tracking-tight text-foreground">
            Genesis
          </span>
        )}
        <button
          onClick={() => setCollapsed((prev) => !prev)}
          className="ml-auto flex h-7 w-7 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-2 py-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.label}
              disabled={!item.active}
              className={cn(
                "group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                item.active
                  ? "bg-white/5 text-foreground"
                  : "cursor-not-allowed text-muted-foreground/60",
                item.active && "hover:bg-white/[0.07]"
              )}
              title={collapsed ? item.label : undefined}
            >
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  item.active
                    ? "text-primary"
                    : "text-muted-foreground/60"
                )}
              />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-border px-4 py-3">
        {!collapsed && (
          <p className="text-xs text-muted-foreground/60">
            Genesis Runtime
          </p>
        )}
      </div>
    </motion.aside>
  );
}