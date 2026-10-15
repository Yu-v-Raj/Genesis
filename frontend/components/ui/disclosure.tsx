import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

/** Expandable technical detail, built on native <details> for keyboard and screen-reader support. */
export function Disclosure({ summary, children, defaultOpen = false, className }: { summary: ReactNode; children: ReactNode; defaultOpen?: boolean; className?: string }) {
  return (
    <details open={defaultOpen} className={cn("group rounded-md border border-border bg-surface", className)}>
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-md px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="h-3.5 w-3.5 transition-transform duration-150 group-open:rotate-90" />
        {summary}
      </summary>
      <div className="border-t border-border px-3 py-3">{children}</div>
    </details>
  );
}

/** Read-only JSON or text, in the mono font. */
export function JsonView({ value, className }: { value: unknown; className?: string }) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return <pre className={cn("max-h-64 overflow-auto rounded-md border border-border bg-background p-3 font-mono text-xs leading-5 text-foreground/90", className)}>{text}</pre>;
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return <kbd className={cn("inline-flex h-5 min-w-5 items-center justify-center rounded border border-border-strong bg-surface-2 px-1 font-mono text-[10px] text-muted-foreground", className)}>{children}</kbd>;
}
