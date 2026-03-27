import { GlassCard } from "../ui/GlassCard";
import { StatusDot } from "../ui/StatusDot";
import type { ModelPerformance } from "../../types/api";

interface ModelStatusCardProps {
  model: ModelPerformance;
}

export function ModelStatusCard({ model }: ModelStatusCardProps) {
  return (
    <GlassCard className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium text-[var(--text-primary)]">
          {model.name}
        </span>
        <StatusDot
          status={
            model.status === "online"
              ? "online"
              : model.status === "degraded"
              ? "warning"
              : "offline"
          }
          size="sm"
          pulse={model.status === "online"}
        />
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <p className="text-[var(--text-muted)]">Requests</p>
          <p className="font-semibold text-[var(--text-primary)]">
            {model.requestCount.toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-[var(--text-muted)]">Error Rate</p>
          <p className="font-semibold text-[var(--text-primary)]">
            {model.errorRate.toFixed(2)}%
          </p>
        </div>
        <div>
          <p className="text-[var(--text-muted)]">Avg Latency</p>
          <p className="font-semibold text-[var(--text-primary)]">
            {model.avgLatency}ms
          </p>
        </div>
        <div>
          <p className="text-[var(--text-muted)]">P95 Latency</p>
          <p className="font-semibold text-[var(--text-primary)]">
            {model.p95Latency}ms
          </p>
        </div>
      </div>
    </GlassCard>
  );
}
