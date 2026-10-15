import { useId, type ComponentProps, type ReactNode } from "react";
import { cn } from "@/lib/utils";

const CONTROL =
  "w-full rounded-md border border-border-strong bg-surface-2 px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-danger";

/**
 * A labelled form control. The child receives the generated id through `children(id)`,
 * so label, hint and error are always associated with it.
 */
export function Field({ label, hint, error, children, className }: { label: ReactNode; hint?: ReactNode; error?: ReactNode; children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode; className?: string }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-xs font-medium text-foreground">{label}</label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && <p id={hintId} className="text-xs text-muted-foreground">{hint}</p>}
      {error && <p id={errorId} className="text-xs text-danger">{error}</p>}
    </div>
  );
}

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(CONTROL, className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(CONTROL, "min-h-24 resize-y leading-6", className)} {...props} />;
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(CONTROL, "appearance-auto pr-8", className)} {...props} />;
}
