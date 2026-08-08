export function AgentListSkeleton() {
  return (
    <div className="grid gap-4">
      {Array.from({ length: 3 }, (_, index) => (
        <div key={index} className="skeleton-shimmer rounded-xl border border-border bg-surface p-6 shadow-sm">
          <div className="h-4 w-36 rounded bg-white/[0.07]" />
          <div className="mt-3 h-3 w-4/5 rounded bg-white/[0.06]" />
          <div className="mt-2 h-3 w-3/5 rounded bg-white/[0.06]" />
          <div className="mt-6 h-8 w-44 rounded-md bg-white/[0.06]" />
        </div>
      ))}
    </div>
  );
}
