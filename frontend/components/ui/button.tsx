import type { ButtonHTMLAttributes, ReactNode } from "react";
import { LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-foreground hover:bg-accent/90",
  secondary: "border border-border bg-surface-2 text-foreground hover:border-border-strong hover:bg-elevated",
  ghost: "text-muted-foreground hover:bg-white/[0.05] hover:text-foreground",
  danger: "border tone-danger tone-border tone-bg tone-fg hover:bg-danger/15",
};

const SIZES: Record<Size, string> = {
  // Touch screens get at least 40px-tall targets.
  sm: "h-8 gap-1.5 px-3 text-xs pointer-coarse:h-10",
  md: "h-9 gap-2 px-3.5 text-sm pointer-coarse:h-10",
};

const BASE =
  "inline-flex shrink-0 items-center justify-center rounded-md font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45";

/** Button styling for elements that are not buttons, such as a Next.js <Link>. */
export function buttonClasses(variant: Variant = "secondary", size: Size = "md", className?: string): string {
  return cn(BASE, VARIANTS[variant], SIZES[size], className);
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Shows a spinner and disables the button while an action runs. */
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({ variant = "secondary", size = "md", loading = false, icon, className, children, disabled, type = "button", ...props }: ButtonProps) {
  return (
    <button type={type} disabled={disabled || loading} aria-busy={loading || undefined} className={cn(BASE, VARIANTS[variant], SIZES[size], className)} {...props}>
      {loading ? <LoaderCircle aria-hidden className="h-3.5 w-3.5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  /** Required: icon-only controls need an accessible name. */
  label: string;
  variant?: Exclude<Variant, "primary">;
}

export function IconButton({ label, variant = "ghost", className, children, type = "button", ...props }: IconButtonProps) {
  return (
    <button type={type} aria-label={label} title={label} className={cn(BASE, VARIANTS[variant], "h-8 w-8 pointer-coarse:h-10 pointer-coarse:w-10", className)} {...props}>
      {children}
    </button>
  );
}
