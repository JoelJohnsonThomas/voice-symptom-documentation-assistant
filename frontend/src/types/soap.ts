export type SOAPSectionKey = "chiefComplaint" | "clinicalDetails" | "subjective" | "objective" | "assessment" | "plan";

export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface SOAPSectionState {
  content: string;
  originalContent: string;
  status: ApprovalStatus;
  isEditing: boolean;
  editHistory: EditHistoryEntry[];
}

export interface EditHistoryEntry {
  timestamp: string;
  previousContent: string;
  newContent: string;
  action: "edit" | "approve" | "reject" | "restore";
  userId?: string;
}

export const SOAP_SECTION_META: Record<SOAPSectionKey, { label: string; shortLabel: string; color: string; bgColor: string }> = {
  chiefComplaint: {
    label: "Chief Complaint",
    shortLabel: "CC",
    color: "var(--cyan-500, #06b6d4)",
    bgColor: "rgba(6, 182, 212, 0.1)",
  },
  clinicalDetails: {
    label: "Clinical Details",
    shortLabel: "CD",
    color: "var(--indigo-500, #6366f1)",
    bgColor: "rgba(99, 102, 241, 0.1)",
  },
  subjective: {
    label: "Subjective",
    shortLabel: "S",
    color: "var(--blue-500, #3b82f6)",
    bgColor: "rgba(59, 130, 246, 0.1)",
  },
  objective: {
    label: "Objective",
    shortLabel: "O",
    color: "var(--emerald-500, #10b981)",
    bgColor: "rgba(16, 185, 129, 0.1)",
  },
  assessment: {
    label: "Assessment",
    shortLabel: "A",
    color: "var(--amber-500, #f59e0b)",
    bgColor: "rgba(245, 158, 11, 0.1)",
  },
  plan: {
    label: "Plan",
    shortLabel: "P",
    color: "var(--rose-500, #f43f5e)",
    bgColor: "rgba(244, 63, 94, 0.1)",
  },
};
