import { cn } from "@/lib/utils";

/** The Genesis mark: an origin node with one orbiting satellite. Decorative by default. */
export function GenesisMark({ className, title }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" role={title ? "img" : undefined} aria-hidden={title ? undefined : true} aria-label={title} className={cn("h-7 w-7", className)}>
      <ellipse cx="16" cy="16" rx="12.5" ry="6.5" transform="rotate(-28 16 16)" stroke="var(--color-accent)" strokeOpacity="0.45" strokeWidth="1.5" />
      <circle cx="16" cy="16" r="4" fill="var(--color-accent)" />
      <circle cx="16" cy="16" r="7" fill="var(--color-accent)" fillOpacity="0.08" />
      <circle cx="26.2" cy="10.6" r="2.2" fill="var(--color-accent-2)" />
    </svg>
  );
}
