"use client";

import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";

import { SectionHeader } from "@/components/dashboard/section-header";
import { StatusCard } from "@/components/dashboard/status-card";
import { StatsCard } from "@/components/dashboard/stats-card";
import { ServicesList } from "@/components/dashboard/services-list";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { LiveLogViewer } from "@/components/dashboard/live-log-viewer";
import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { RealtimeStatus } from "@/components/dashboard/realtime-status";

import {
  StatusCardSkeleton,
  StatsCardSkeleton,
  ServicesListSkeleton,
  RecentActivitySkeleton,
} from "@/components/dashboard/skeletons";

import { ErrorState } from "@/components/dashboard/error-state";
import { useSystemDashboard } from "@/hooks/use-system";

export default function Home() {
  const { data, loading, error, connectionStatus } = useSystemDashboard();

  // True only during the very first dashboard load.
  const isInitialLoading = loading && data === null;

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar />

      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />

        <main className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto flex max-w-6xl flex-col gap-10">
            {data && <RealtimeNotifications events={data.events} />}

            {/* Dashboard Header */}
            <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
              <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                  Genesis Dashboard
                </h1>

                <p className="text-sm text-muted-foreground">
                  Agent Operating System
                </p>

                <p className="mt-1 text-sm text-muted-foreground/80">
                  An overview of your runtime, services, and recent activity.
                </p>
                <RealtimeStatus
                  connectionStatus={connectionStatus}
                  runtimeState={data?.runtimeState ?? "loading"}
                  lastHeartbeat={data?.lastHeartbeat ?? null}
                />
              </div>
            </div>

            {/* Initial load failed */}
            {error && !data ? (
              <ErrorState
                message={error}
              />
            ) : (
              <>
                {/* Background refresh failed */}
                {error && data && (
                  <div className="rounded-md border border-red-500/30 bg-red-500/5 px-4 py-3 text-xs text-red-300">
                    Failed to refresh: {error}. Showing the last successfully
                    loaded dashboard.
                  </div>
                )}

                {/* Status Cards */}
                <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {isInitialLoading
                    ? Array.from({ length: 4 }, (_, index) => (
                        <StatusCardSkeleton
                          key={`status-skeleton-${index}`}
                        />
                      ))
                    : data?.statusCards.map((card) => (
                        <StatusCard key={card.title} {...card} />
                      ))}
                </section>

                {/* Services */}
                <section className="flex flex-col gap-3">
                  <SectionHeader
                    title="Registered Services"
                    description="Core services currently running in the Genesis runtime."
                  />

                  {isInitialLoading ? (
                    <ServicesListSkeleton />
                  ) : (
                    data && <ServicesList services={data.services} />
                  )}
                </section>

                {/* Statistics */}
                <section className="flex flex-col gap-3">
                  <SectionHeader title="Statistics" />

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {isInitialLoading
                      ? Array.from({ length: 4 }, (_, index) => (
                          <StatsCardSkeleton
                            key={`stats-skeleton-${index}`}
                          />
                        ))
                      : data?.stats.map((stat) => (
                          <StatsCard key={stat.label} {...stat} />
                        ))}
                  </div>
                </section>

                {/* Recent Activity */}
                <section className="flex flex-col gap-3">
                  <SectionHeader title="Recent Activity" />

                  {isInitialLoading ? (
                    <RecentActivitySkeleton />
                  ) : (
                    data && (
                      <RecentActivity items={data.activity} />
                    )
                  )}
                </section>

                {/* Live Logs */}
                <section className="flex flex-col gap-3">
                  <SectionHeader
                    title="Live Logs"
                    description="Structured logs streamed from the Genesis runtime."
                  />
                  {data && <LiveLogViewer events={data.events} />}
                </section>
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
