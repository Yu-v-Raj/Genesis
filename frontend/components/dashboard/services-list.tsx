"use client";

import { motion } from "framer-motion";

export type ServiceStatus = "online" | "degraded" | "offline";

export interface ServiceItem {
  name: string;
  description: string;
  status: ServiceStatus;
}

interface ServicesListProps {
  services: ServiceItem[];
}

const statusColor: Record<ServiceStatus, string> = {
  online: "bg-success",
  degraded: "bg-yellow-500",
  offline: "bg-red-500",
};

const statusLabel: Record<ServiceStatus, string> = {
  online: "Online",
  degraded: "Degraded",
  offline: "Offline",
};

export function ServicesList({ services }: ServicesListProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {services.map((service, index) => (
        <motion.div
          key={service.name}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, delay: index * 0.03, ease: "easeOut" }}
          title={service.description}
          className="flex items-center justify-between gap-4 rounded-xl border border-border bg-surface px-4 py-3 shadow-sm transition-all hover:-translate-y-0.5 hover:border-white/15 hover:shadow-lg hover:shadow-black/15"
        >
          <div className="flex items-center gap-3">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${statusColor[service.status]}`}
              aria-hidden="true"
            />
            <div className="flex flex-col">
              <span className="text-sm font-medium text-foreground">
                {service.name}
              </span>
              <span className="text-xs text-muted-foreground">
                {service.description}
              </span>
            </div>
          </div>
          <span className={`shrink-0 rounded-full border px-2 py-1 text-[11px] font-medium ${service.status === "online" ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-200" : service.status === "degraded" ? "border-amber-400/20 bg-amber-400/10 text-amber-200" : "border-red-400/20 bg-red-400/10 text-red-200"}`}>{statusLabel[service.status]}</span>
        </motion.div>
      ))}
    </div>
  );
}
