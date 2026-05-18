import { useState } from "react";
import { History } from "lucide-react";
import { useSessionStore } from "../../stores/sessionStore";
import { SOAPSectionCard } from "./SOAPSectionCard";
import { ClinicalReviewNotice } from "./ClinicalReviewNotice";
import { NEREntitiesCard } from "./NEREntitiesCard";
import { AnnotationDrawer } from "./AnnotationDrawer";
import { ApprovalButton } from "./ApprovalButton";
import { EditHistoryPanel } from "./EditHistoryPanel";
import { GlassCard } from "../ui/GlassCard";
import { useVersionList } from "../../hooks/useSoapReview";
import type { SOAPSectionKey } from "../../types/soap";

const SECTION_ORDER: SOAPSectionKey[] = [
  "chiefComplaint",
  "clinicalDetails",
  "subjective",
  "objective",
  "assessment",
  "plan",
];

interface ResultsContainerProps {
  sessionId?: string;
}

export function ResultsContainer({ sessionId }: ResultsContainerProps) {
  const {
    documentation,
    soapSections,
    approveSOAPSection,
    rejectSOAPSection,
    updateSOAPSection,
    startEditingSOAP,
    cancelEditingSOAP,
    restoreSOAPSection,
  } = useSessionStore();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const versions = useVersionList(sessionId);
  const currentVersionId = versions.data?.[0]?.id ?? null;

  if (!documentation) return null;

  return (
    <div className="space-y-4">
      <ClinicalReviewNotice
        sessionId={sessionId}
        onOpenAnnotations={sessionId ? () => setDrawerOpen(true) : undefined}
      />

      {sessionId && (
        <GlassCard className="flex flex-wrap items-center justify-between gap-2 p-3">
          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            <span className="font-medium text-[var(--text-secondary)]">
              {versions.data?.length ?? 0} saved version{versions.data?.length === 1 ? "" : "s"}
            </span>
            {currentVersionId && (
              <span className="rounded bg-white/[0.06] px-1.5 py-0.5">
                Current: v{versions.data?.[0]?.version_number}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setHistoryOpen((v) => !v)}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-primary)] px-2 py-1 text-xs text-[var(--text-secondary)] hover:bg-white/[0.04]"
            >
              <History size={12} />
              {historyOpen ? "Hide history" : "Version history"}
            </button>
            <ApprovalButton sessionId={sessionId} versionId={currentVersionId} size="sm" />
          </div>
        </GlassCard>
      )}

      {sessionId && historyOpen && (
        <GlassCard className="p-3">
          <EditHistoryPanel sessionId={sessionId} />
        </GlassCard>
      )}

      {SECTION_ORDER.map((key) => (
        <SOAPSectionCard
          key={key}
          sectionKey={key}
          state={soapSections[key]}
          confidence={documentation.confidence?.overall}
          onApprove={() => approveSOAPSection(key)}
          onReject={() => rejectSOAPSection(key)}
          onEdit={(content) => updateSOAPSection(key, content)}
          onStartEdit={() => startEditingSOAP(key)}
          onCancelEdit={() => cancelEditingSOAP(key)}
          onRestore={(index) => restoreSOAPSection(key, index)}
        />
      ))}

      {documentation.nerEntities && (
        <NEREntitiesCard entities={documentation.nerEntities} />
      )}

      {sessionId && (
        <AnnotationDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          sessionId={sessionId}
          currentVersionId={currentVersionId}
        />
      )}
    </div>
  );
}
