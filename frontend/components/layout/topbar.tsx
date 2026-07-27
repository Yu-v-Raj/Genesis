"use client";

import { useState } from "react";
import { Moon, Sun, Globe } from "lucide-react";
import { cn } from "@/lib/utils";

export function Topbar() {
  const [isDark, setIsDark] = useState(true);

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background px-6">
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-foreground">Genesis</span>
        <span className="rounded-full border border-border bg-surface px-2 py-0.5 text-xs font-medium text-muted-foreground">
          v0.1.0
        </span>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => setIsDark((prev) => !prev)}
          aria-label="Toggle theme"
          className={cn(
            "flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground",
            "transition-colors hover:bg-white/5 hover:text-foreground"
          )}
        >
          {isDark ? (
            <Moon className="h-4 w-4" />
          ) : (
            <Sun className="h-4 w-4" />
          )}
        </button>

        <button
          aria-label="GitHub"
          className="flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground"
        >
          <Globe className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}