import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** One h1 per page, with an optional description and actions on the right. */
export function PageHeader({ title, description, meta, actions, className }: { title: ReactNode; description?: ReactNode; meta?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <header className={cn("flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        {meta && <div className="mt-2">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
