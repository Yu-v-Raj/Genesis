"use client";

import { motion } from "framer-motion";
import { Wrench, Puzzle, BrainCircuit, Workflow, type LucideIcon } from "lucide-react";

export type StatsCardIcon = "wrench" | "puzzle" | "brainCircuit" | "workflow";

const iconMap: Record<StatsCardIcon, LucideIcon> = {
  wrench: Wrench,
  puzzle: Puzzle,
  brainCircuit: BrainCircuit,
  workflow: Workflow,
};

export interface StatsCardData {
  icon: StatsCardIcon;
  label: string;
  value: string;
}

export function StatsCard({ icon, label, value }: StatsCardData) {
  const Icon = iconMap[icon];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      whileHover={{ y: -2 }}
      className="flex items-center justify-between rounded-lg border border-border bg-surface p-4"
    >
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <span className="text-lg font-semibold text-foreground">{value}</span>
    </motion.div>
  );
}