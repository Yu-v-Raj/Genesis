function SkeletonBlock({
  className,
}: {
  className: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded bg-white/5 ${className}`}
    />
  );
}

export function StatusCardSkeleton() {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center gap-2">
        <SkeletonBlock className="h-7 w-7 rounded-md" />
        <SkeletonBlock className="h-3 w-16" />
      </div>

      <SkeletonBlock className="h-7 w-20" />
      <SkeletonBlock className="h-3 w-32" />
    </div>
  );
}

export function StatsCardSkeleton() {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center gap-2">
        <SkeletonBlock className="h-4 w-4" />
        <SkeletonBlock className="h-3 w-20" />
      </div>

      <SkeletonBlock className="h-5 w-8" />
    </div>
  );
}

export function ServicesListSkeleton() {
  return (
    <div className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface">
      {Array.from({ length: 6 }, (_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 px-4 py-3"
        >
          <SkeletonBlock className="h-2 w-2 rounded-full bg-white/10" />

          <div className="flex flex-1 flex-col gap-2">
            <SkeletonBlock className="h-3 w-32" />
            <SkeletonBlock className="h-3 w-48" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function RecentActivitySkeleton() {
  return (
    <div className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface">
      {Array.from({ length: 4 }, (_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 px-4 py-3"
        >
          <SkeletonBlock className="h-4 w-4 rounded-full" />
          <SkeletonBlock className="h-3 flex-1" />
          <SkeletonBlock className="h-3 w-14" />
        </div>
      ))}
    </div>
  );
}