import { Layers } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import type { QueueStatus } from "../../types/api";

interface QueueCardProps {
  queue: QueueStatus;
}

export function QueueCard({ queue }: QueueCardProps) {
  const utilization = Math.round((queue.active / queue.maxConcurrent) * 100);

  return (
    <GlassCard className="p-5">
      <div className="mb-3 flex items-center gap-2 text-[var(--text-muted)]">
        <Layers size={14} />
        <span className="text-xs font-semibold uppercase tracking-wider">
          Processing Queue
        </span>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-[var(--text-muted)]">Active</p>
          <p className="text-xl font-bold text-[var(--text-primary)]">
            {queue.active}
          </p>
        </div>
        <div>
          <p className="text-xs text-[var(--text-muted)]">Queued</p>
          <p className="text-xl font-bold text-[var(--text-primary)]">
            {queue.queued}
          </p>
        </div>
      </div>
      <div className="mt-3">
        <div className="mb-1 flex justify-between text-xs text-[var(--text-muted)]">
          <span>Utilization</span>
          <span>{utilization}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[var(--bg-primary)]">
          <div
            className="h-full rounded-full bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-secondary)] transition-all"
            style={{ width: `${utilization}%` }}
          />
        </div>
      </div>
    </GlassCard>
  );
}
