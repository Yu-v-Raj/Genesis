import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({ icon: Icon, title, description, action, className }: { icon?: LucideIcon; title: string; description?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center rounded-lg border border-dashed border-border bg-surface px-6 py-12 text-center", className)}>
      {Icon && (
        <span className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-surface-2 text-accent">
          <Icon aria-hidden className="h-5 w-5" />
        </span>
      )}
      <h2 className="mt-3 text-sm font-semibold text-foreground">{title}</h2>
      {description && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("skeleton-shimmer rounded-md bg-surface-2", className)} />;
}

/** An inline alert. `danger` and `warning` are announced by screen readers. */
export function Alert({ tone = "info", children, action, className }: { tone?: "info" | "warning" | "danger" | "success"; children: ReactNode; action?: ReactNode; className?: string }) {
  const urgent = tone === "danger" || tone === "warning";
  return (
    <div role={urgent ? "alert" : "status"} className={cn("flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm", `tone-${tone}`, "tone-bg tone-border text-foreground", className)}>
      <div className="min-w-0">{children}</div>
      {action}
    </div>
  );
}
