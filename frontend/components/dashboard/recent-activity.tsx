"use client";

import { motion } from "framer-motion";
import { CheckCircle2 } from "lucide-react";

export interface ActivityItem {
  id: string;
  title: string;
  timestamp: string;
}

interface RecentActivityProps {
  items: ActivityItem[];
}

export function RecentActivity({ items }: RecentActivityProps) {
  return (
    <div className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface">
      {items.length === 0 ? (
        <p className="px-4 py-6 text-xs text-muted-foreground">Waiting for live runtime events.</p>
      ) : items.map((item, index) => (
        <motion.div
          key={item.id}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, delay: index * 0.03, ease: "easeOut" }}
          className="flex items-center gap-3 px-4 py-3"
        >
          <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
          <span className="flex-1 text-sm text-foreground">{item.title}</span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {item.timestamp}
          </span>
        </motion.div>
      ))}
    </div>
  );
}
