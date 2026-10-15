import { agentInitials } from "@/lib/agent-directory";
import { cn } from "@/lib/utils";

/** An Agent's initials on a quiet tile; decorative, the name is always shown alongside. */
export function AgentAvatar({ name, size = "md", className }: { name: string; size?: "sm" | "md" | "lg"; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 select-none items-center justify-center rounded-md border border-border-strong bg-surface-2 font-semibold text-foreground/85",
        size === "sm" ? "h-7 w-7 text-[10px]" : size === "lg" ? "h-11 w-11 text-sm" : "h-9 w-9 text-xs",
        className,
      )}
    >
      {agentInitials(name)}
    </span>
  );
}
