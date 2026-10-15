import { CheckCircle2, CircleAlert, CircleDashed, Info, LoaderCircle, PauseCircle, type LucideIcon } from "lucide-react";
import { statusPresentation, type StatusTone } from "@/lib/status";
import { cn } from "@/lib/utils";

const ICONS: Record<StatusTone, LucideIcon> = {
  success: CheckCircle2,
  danger: CircleAlert,
  warning: PauseCircle,
  info: Info,
  running: LoaderCircle,
  neutral: CircleDashed,
};

/** Status as icon + text, never color alone. */
export function StatusBadge({ status, label, className }: { status: string | null | undefined; label?: string; className?: string }) {
  const presentation = statusPresentation(status);
  const Icon = ICONS[presentation.tone];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium", `tone-${presentation.tone}`, "tone-fg tone-bg tone-border", className)}>
      <Icon aria-hidden className={cn("h-3 w-3", presentation.tone === "running" && "animate-spin")} />
      {label ?? presentation.label}
    </span>
  );
}

/** A small colored dot; pair it with visible text. */
export function StatusDot({ tone, pulse = false, className }: { tone: StatusTone; pulse?: boolean; className?: string }) {
  return <span aria-hidden className={cn("inline-block h-1.5 w-1.5 shrink-0 rounded-full tone-dot", `tone-${tone}`, pulse && "animate-soft-pulse", className)} />;
}
