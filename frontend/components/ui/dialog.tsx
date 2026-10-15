"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { IconButton } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  /** `drawer` slides in from the left edge (mobile navigation); `sheet` from the right (detail panels). */
  variant?: "dialog" | "drawer" | "sheet";
  /** Dialog width; `lg` suits forms with several sections. */
  size?: "md" | "lg";
  /** Pinned below the scrolling body, e.g. form actions. */
  footer?: ReactNode;
  /**
   * `palette`: a top-anchored panel whose content supplies its own layout and close control
   * (the title stays as the accessible name). Same focus trap, inertness and Escape handling.
   */
  layout?: "default" | "palette";
  /** Hide the visible title while keeping it as the accessible name. */
  hideTitle?: boolean;
  className?: string;
}

/**
 * An accessible modal: the rest of the page is made inert, focus moves inside and stays
 * there, Escape and the backdrop close it, and focus returns to the opener afterwards.
 */
export function Dialog({ open, onClose, title, description, children, variant = "dialog", size = "md", layout = "default", footer, hideTitle = false, className }: DialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const container = panel.closest<HTMLElement>("[data-dialog-root]");

    // Make everything outside the dialog inert, restoring only what we changed.
    const madeInert = Array.from(document.body.children).filter(
      (element): element is HTMLElement => element instanceof HTMLElement && element !== container && !element.inert,
    );
    madeInert.forEach((element) => { element.inert = true; });
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    (panel.querySelector<HTMLElement>("[data-autofocus]") ?? panel.querySelector<HTMLElement>(FOCUSABLE) ?? panel).focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      madeInert.forEach((element) => { element.inert = false; });
      document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus();
    };
  }, [open]);

  if (!open || typeof document === "undefined") return null;

  const drawer = variant === "drawer";
  const sheet = variant === "sheet";
  const palette = layout === "palette";
  return createPortal(
    <div data-dialog-root className={cn("fixed inset-0 z-50 flex", drawer ? "items-stretch justify-start" : sheet ? "items-stretch justify-end" : palette ? "items-start justify-center px-3 pt-[12dvh] sm:px-4" : "items-end justify-center p-0 sm:items-center sm:p-4")}>
      <div aria-hidden className="absolute inset-0 animate-overlay-in bg-black/60 backdrop-blur-[2px]" onClick={() => onCloseRef.current()} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        data-command-palette={palette || undefined}
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          "relative flex max-h-full flex-col border-border bg-elevated shadow-overlay outline-none",
          drawer
            ? "h-full w-72 max-w-[85vw] animate-drawer-in border-r"
            : sheet
              ? "h-full w-full animate-sheet-in border-l sm:w-[30rem]"
              : palette
                ? "max-h-[70dvh] w-full max-w-xl animate-dialog-in overflow-hidden rounded-lg border"
                : cn("max-h-[90dvh] w-full animate-dialog-in rounded-t-lg border sm:rounded-lg", size === "lg" ? "sm:max-w-2xl" : "sm:max-w-lg"),
          className,
        )}
      >
        {palette ? (
          <>
            <h2 id={titleId} className="sr-only">{title}</h2>
            {description && <p id={descriptionId} className="sr-only">{description}</p>}
            {children}
          </>
        ) : (<>
        <div className={cn("flex items-start justify-between gap-3 px-4 pt-4", hideTitle && "pt-3")}>
          <div className={cn("min-w-0", hideTitle && "sr-only")}>
            <h2 id={titleId} className="text-base font-semibold text-foreground">{title}</h2>
            {description && <p id={descriptionId} className="mt-1 text-sm text-muted-foreground">{description}</p>}
          </div>
          <IconButton label="Close" onClick={() => onCloseRef.current()} className="-mr-1 ml-auto">
            <X aria-hidden className="h-4 w-4" />
          </IconButton>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 pt-3">{children}</div>
        {footer && <div className="shrink-0 border-t border-border px-4 py-3">{footer}</div>}
        </>)}
      </div>
    </div>,
    document.body,
  );
}
