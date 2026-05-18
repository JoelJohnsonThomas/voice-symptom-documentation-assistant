import { ArrowRight } from "lucide-react";
import type { VersionDiff, SOAPReviewSection } from "../../types/soapReview";

const SECTION_LABEL: Record<SOAPReviewSection, string> = {
  subjective: "Subjective",
  objective: "Objective",
  assessment: "Assessment",
  plan: "Plan",
};

interface VersionDiffViewProps {
  diff: VersionDiff | null | undefined;
}

export function VersionDiffView({ diff }: VersionDiffViewProps) {
  if (!diff || Object.keys(diff).length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-[var(--border-primary)] p-3 text-center text-xs text-[var(--text-muted)]">
        No changes between versions
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {Object.entries(diff).map(([section, change]) => (
        <div key={section} className="rounded-lg border border-[var(--border-primary)] p-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
            {SECTION_LABEL[section as SOAPReviewSection] ?? section}
          </p>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_auto_1fr] md:items-center">
            <div className="rounded bg-[var(--status-error)]/5 p-2 text-xs text-[var(--text-secondary)]">
              {change?.before ?? <span className="italic text-[var(--text-muted)]">empty</span>}
            </div>
            <ArrowRight size={14} className="mx-auto text-[var(--text-muted)]" />
            <div className="rounded bg-[var(--status-online)]/5 p-2 text-xs text-[var(--text-primary)]">
              {change?.after ?? <span className="italic text-[var(--text-muted)]">removed</span>}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
