"use client";

import { AlertTriangle } from "lucide-react";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
  isRetrying?: boolean;
}

export function ErrorState({
  message,
  onRetry,
  isRetrying = false,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex flex-col items-center gap-4 rounded-lg border border-border bg-surface p-10 text-center"
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-white/[0.03]">
        <AlertTriangle className="h-5 w-5 text-red-400" />
      </div>

      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-foreground">
          Couldn't load the dashboard
        </p>

        <p className="text-xs text-muted-foreground">
          {message}
        </p>
      </div>

      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={isRetrying}
          className="rounded-md border border-border bg-white/[0.03] px-4 py-2 text-xs font-medium text-foreground transition-colors hover:bg-white/[0.07] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isRetrying ? "Retrying..." : "Retry"}
        </button>
      )}
    </div>
  );
}
