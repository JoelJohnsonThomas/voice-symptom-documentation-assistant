import { Check, Loader2, Circle } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { cn } from "../../lib/utils";
import type { PipelineStage } from "../../types/api";

interface PipelineProgressProps {
  stages: PipelineStage[];
  currentStage: string | null;
}

export function PipelineProgress({ stages, currentStage }: PipelineProgressProps) {
  if (stages.length === 0) return null;

  return (
    <GlassCard className="p-5">
      <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Processing Pipeline
      </h4>
      <div className="space-y-2">
        {stages.map((stage) => (
          <div key={stage.name} className="flex items-center gap-3">
            {stage.status === "completed" ? (
              <Check size={14} className="text-[var(--status-online)]" />
            ) : stage.status === "active" ? (
              <Loader2 size={14} className="animate-spin text-[var(--accent-primary)]" />
            ) : stage.status === "error" ? (
              <Circle size={14} className="text-[var(--status-error)]" />
            ) : (
              <Circle size={14} className="text-[var(--text-muted)]" />
            )}
            <span
              className={cn(
                "text-sm",
                stage.status === "active"
                  ? "font-medium text-[var(--text-primary)]"
                  : stage.status === "completed"
                  ? "text-[var(--text-secondary)]"
                  : "text-[var(--text-muted)]"
              )}
            >
              {stage.name}
            </span>
            {stage.duration !== undefined && (
              <span className="ml-auto text-xs text-[var(--text-muted)]">
                {stage.duration}ms
              </span>
            )}
          </div>
        ))}
      </div>
    </GlassCard>
  );
}
