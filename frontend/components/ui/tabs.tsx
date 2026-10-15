"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TabItem<T extends string> {
  value: T;
  label: string;
  /** Optional count or short hint shown after the label. */
  badge?: ReactNode;
}

const tabId = (idPrefix: string, value: string) => `${idPrefix}-tab-${value}`;
const panelId = (idPrefix: string, value: string) => `${idPrefix}-panel-${value}`;

/** Props for the panel of the selected tab, so it is labelled by and controlled from its tab. */
export function tabPanelProps(idPrefix: string, value: string) {
  return { id: panelId(idPrefix, value), role: "tabpanel" as const, "aria-labelledby": tabId(idPrefix, value), tabIndex: 0 };
}

/**
 * WAI-ARIA tabs with automatic activation: arrow keys, Home and End move between tabs, and
 * only the selected tab is in the tab order. The parent owns the selected value (so it can
 * live in the URL) and renders the panel with `tabPanelProps(idPrefix, value)`.
 */
export function Tabs<T extends string>({ items, value, onChange, label, idPrefix, className }: { items: readonly TabItem<T>[]; value: T; onChange: (value: T) => void; label: string; idPrefix: string; className?: string }) {
  const refs = useRef(new Map<T, HTMLButtonElement>());

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const index = items.findIndex((item) => item.value === value);
    const last = items.length - 1;
    const next = event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (next === null) return;
    event.preventDefault();
    const target = items[next].value;
    onChange(target);
    refs.current.get(target)?.focus();
  }

  return (
    <div role="tablist" aria-label={label} className={cn("flex gap-1 overflow-x-auto border-b border-border [scrollbar-width:none] [&::-webkit-scrollbar]:hidden", className)}>
      {items.map((item) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            ref={(element) => { if (element) refs.current.set(item.value, element); else refs.current.delete(item.value); }}
            type="button"
            role="tab"
            id={tabId(idPrefix, item.value)}
            aria-selected={selected}
            aria-controls={panelId(idPrefix, item.value)}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.value)}
            onKeyDown={onKeyDown}
            className={cn(
              "relative -mb-px flex h-10 shrink-0 items-center gap-2 border-b-2 px-3 text-sm transition-colors duration-150",
              selected ? "border-accent font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
            {item.badge !== undefined && <span className="rounded-full bg-surface-2 px-1.5 text-[11px] tabular-nums text-muted-foreground">{item.badge}</span>}
          </button>
        );
      })}
    </div>
  );
}
