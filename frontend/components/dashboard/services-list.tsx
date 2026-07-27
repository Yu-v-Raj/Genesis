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
    <div className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface">
      {services.map((service, index) => (
        <motion.div
          key={service.name}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, delay: index * 0.03, ease: "easeOut" }}
          className="flex items-center justify-between gap-4 px-4 py-3"
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
          <span className="shrink-0 text-xs text-muted-foreground">
            {statusLabel[service.status]}
          </span>
        </motion.div>
      ))}
    </div>
  );
}