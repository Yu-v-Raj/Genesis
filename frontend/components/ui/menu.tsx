"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface MenuItem {
  key: string;
  label: ReactNode;
  /** Secondary text under the label. */
  description?: ReactNode;
  icon?: ReactNode;
  onSelect: () => void;
  disabled?: boolean;
  danger?: boolean;
  /** Renders a selection mark (menuitemradio) when defined. */
  checked?: boolean;
}

export type MenuEntry = MenuItem | "separator";

/**
 * A menu button (WAI-ARIA pattern): arrow keys, Home/End and type-ahead-free navigation,
 * Escape or Tab closes and focus returns to the trigger. The list is portalled and fixed-
 * positioned, so scrolling containers never clip it.
 */
export function Menu({ trigger, triggerLabel, items, align = "end", className, triggerClassName, width = "w-56", heading }: {
  trigger: ReactNode;
  /** Accessible name for the trigger button. */
  triggerLabel: string;
  items: readonly MenuEntry[];
  align?: "start" | "end";
  className?: string;
  triggerClassName?: string;
  width?: string;
  heading?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ top: number; left?: number; right?: number; maxHeight: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const actionable = items.filter((item): item is MenuItem => item !== "separator");

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    function place() {
      const rect = triggerRef.current!.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom - 8;
      const maxHeight = Math.max(160, Math.min(420, below));
      setPosition(align === "end"
        ? { top: rect.bottom + 4, right: Math.max(8, window.innerWidth - rect.right), maxHeight }
        : { top: rect.bottom + 4, left: Math.max(8, rect.left), maxHeight });
    }
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open, align]);

  const positioned = position !== null;
  useEffect(() => {
    if (!open || !positioned) return;
    const firstEnabled = listRef.current?.querySelector<HTMLElement>('[role^="menuitem"]:not([aria-disabled="true"])');
    (listRef.current?.querySelector<HTMLElement>('[aria-checked="true"]') ?? firstEnabled)?.focus();
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (!listRef.current?.contains(target) && !triggerRef.current?.contains(target)) setOpen(false);
    }
    function onScroll(event: Event) {
      if (!listRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, positioned]);

  function close(returnFocus = true) {
    setOpen(false);
    setPosition(null);
    if (returnFocus) triggerRef.current?.focus();
  }

  function onListKeyDown(event: React.KeyboardEvent) {
    const elements = Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]:not([aria-disabled="true"])') ?? []);
    const index = elements.indexOf(document.activeElement as HTMLElement);
    if (event.key === "Escape") { event.preventDefault(); close(); }
    else if (event.key === "Tab") close(false);
    else if (event.key === "ArrowDown") { event.preventDefault(); elements[(index + 1) % elements.length]?.focus(); }
    else if (event.key === "ArrowUp") { event.preventDefault(); elements[(index - 1 + elements.length) % elements.length]?.focus(); }
    else if (event.key === "Home") { event.preventDefault(); elements[0]?.focus(); }
    else if (event.key === "End") { event.preventDefault(); elements[elements.length - 1]?.focus(); }
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={triggerLabel}
        title={triggerLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => { if (event.key === "ArrowDown" && !open) { event.preventDefault(); setOpen(true); } }}
        className={triggerClassName}
      >
        {trigger}
      </button>
      {open && position && createPortal(
        <div
          ref={listRef}
          id={menuId}
          role="menu"
          aria-label={triggerLabel}
          onKeyDown={onListKeyDown}
          style={{ top: position.top, left: position.left, right: position.right, maxHeight: position.maxHeight }}
          className={cn("fixed z-[55] flex animate-dialog-in flex-col overflow-y-auto rounded-lg border border-border bg-elevated p-1 shadow-overlay", width, className)}
        >
          {heading && <div className="px-2.5 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-wider text-subtle">{heading}</div>}
          {items.map((item, index) => item === "separator"
            ? <div key={`separator-${index}`} role="separator" className="my-1 border-t border-border" />
            : (
              <button
                key={item.key}
                type="button"
                role={item.checked === undefined ? "menuitem" : "menuitemradio"}
                aria-checked={item.checked}
                aria-disabled={item.disabled || undefined}
                tabIndex={-1}
                onClick={() => { if (item.disabled) return; close(); item.onSelect(); }}
                className={cn(
                  "flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left text-sm outline-none transition-colors focus:bg-white/[0.07] hover:bg-white/[0.05]",
                  item.danger ? "text-danger" : "text-foreground",
                  item.disabled && "cursor-not-allowed opacity-45 hover:bg-transparent",
                )}
              >
                {item.checked !== undefined
                  ? <Check aria-hidden className={cn("mt-0.5 h-4 w-4 shrink-0 text-accent", !item.checked && "invisible")} />
                  : item.icon && <span aria-hidden className="mt-0.5 shrink-0 text-muted-foreground [&>svg]:h-4 [&>svg]:w-4">{item.icon}</span>}
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{item.label}</span>
                  {item.description && <span className="mt-0.5 block truncate text-xs text-muted-foreground">{item.description}</span>}
                </span>
              </button>
            ))}
          {actionable.length === 0 && <p className="px-2.5 py-2 text-sm text-muted-foreground">Nothing here yet.</p>}
        </div>,
        document.body,
      )}
    </>
  );
}
