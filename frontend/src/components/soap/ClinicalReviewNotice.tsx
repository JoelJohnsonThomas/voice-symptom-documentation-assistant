import { AlertTriangle, MessageSquare } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { useAnnotationList } from "../../hooks/useSoapReview";

interface ClinicalReviewNoticeProps {
  sessionId?: string;
  onOpenAnnotations?: () => void;
}

export function ClinicalReviewNotice({ sessionId, onOpenAnnotations }: ClinicalReviewNoticeProps) {
  const annotations = useAnnotationList(sessionId, { annotation_status: "open" });
  const openCount = annotations.data?.length ?? 0;

  return (
    <GlassCard className="border-[var(--status-warning)]/30 bg-[var(--status-warning)]/5 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle
          size={18}
          className="mt-0.5 shrink-0 text-[var(--status-warning)]"
        />
        <div className="flex-1">
          <p className="text-sm font-medium text-[var(--status-warning)]">
            Clinical Review Required
          </p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            AI-generated documentation must be reviewed and approved by a
            licensed clinician before use. This system is a clinical decision
            support tool and does not replace professional medical judgment.
          </p>
          {sessionId && (
            <button
              type="button"
              onClick={onOpenAnnotations}
              disabled={!onOpenAnnotations}
              className="mt-2 inline-flex items-center gap-1.5 rounded border border-[var(--status-warning)]/30 px-2 py-1 text-xs font-medium text-[var(--status-warning)] hover:bg-[var(--status-warning)]/10 disabled:opacity-50"
            >
              <MessageSquare size={12} />
              {openCount > 0
                ? `${openCount} open annotation${openCount === 1 ? "" : "s"}`
                : "Open annotations"}
            </button>
          )}
        </div>
      </div>
    </GlassCard>
  );
}
