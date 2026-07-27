"use client";

import { motion } from "framer-motion";
import { HeartPulse, Server, Activity, Tag, type LucideIcon } from "lucide-react";

export type StatusCardIcon = "server" | "heartPulse" | "activity" | "tag";

const iconMap: Record<StatusCardIcon, LucideIcon> = {
  server: Server,
  heartPulse: HeartPulse,
  activity: Activity,
  tag: Tag,
};

export interface StatusCardData {
  icon: StatusCardIcon;
  title: string;
  value: string;
  description: string;
}

export function StatusCard({ icon, title, value, description }: StatusCardData) {
  const Icon = iconMap[icon];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      whileHover={{ y: -2 }}
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4"
    >
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-white/[0.03]">
          <Icon className="h-3.5 w-3.5 text-primary" />
        </div>
        <span className="text-xs font-medium text-muted-foreground">{title}</span>
      </div>
      <div className="text-2xl font-semibold tracking-tight text-foreground">
        {value}
      </div>
      <p className="text-xs text-muted-foreground/80">{description}</p>
    </motion.div>
  );
}