import { useSessionStore } from "../../stores/sessionStore";
import { SOAPSectionCard } from "./SOAPSectionCard";
import { ClinicalReviewNotice } from "./ClinicalReviewNotice";
import { NEREntitiesCard } from "./NEREntitiesCard";
import type { SOAPSectionKey } from "../../types/soap";

const SECTION_ORDER: SOAPSectionKey[] = [
  "chiefComplaint",
  "clinicalDetails",
  "subjective",
  "objective",
  "assessment",
  "plan",
];

export function ResultsContainer() {
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

  if (!documentation) return null;

  return (
    <div className="space-y-4">
      <ClinicalReviewNotice />

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
    </div>
  );
}
