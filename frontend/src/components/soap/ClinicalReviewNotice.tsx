import { AlertTriangle } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";

export function ClinicalReviewNotice() {
  return (
    <GlassCard className="border-[var(--status-warning)]/30 bg-[var(--status-warning)]/5 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle
          size={18}
          className="mt-0.5 shrink-0 text-[var(--status-warning)]"
        />
        <div>
          <p className="text-sm font-medium text-[var(--status-warning)]">
            Clinical Review Required
          </p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            AI-generated documentation must be reviewed and approved by a
            licensed clinician before use. This system is a clinical decision
            support tool and does not replace professional medical judgment.
          </p>
        </div>
      </div>
    </GlassCard>
  );
}
