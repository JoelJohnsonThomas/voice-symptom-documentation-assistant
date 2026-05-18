export interface SOAPContent {
  subjective?: string | null;
  objective?: string | null;
  assessment?: string | null;
  plan?: string | null;
}

export type SOAPReviewSection = keyof SOAPContent;

export type ChangeType = "initial" | "edit" | "ai_generated" | "review" | "correction";

export type AnnotationType = "correction" | "addition" | "question" | "approval" | "flag";

export type AnnotationStatus = "open" | "resolved" | "rejected";

export interface VersionSummary {
  id: string;
  session_id: string;
  version_number: number;
  created_at: string;
  author_id: string | null;
  author_username: string | null;
  author_role: string | null;
  change_type: ChangeType;
  change_summary: string | null;
}

export interface VersionDiffEntry {
  before: string | null;
  after: string | null;
}

export type VersionDiff = Partial<Record<SOAPReviewSection, VersionDiffEntry>>;

export interface VersionDetail extends VersionSummary {
  content: SOAPContent;
  diff: VersionDiff | null;
  confidence: Record<string, number> | null;
}

export interface Annotation {
  id: string;
  document_version_id: string;
  session_id: string;
  created_at: string;
  author_id: string | null;
  author_username: string | null;
  soap_section: SOAPReviewSection;
  field_path: string | null;
  text_offset_start: number | null;
  text_offset_end: number | null;
  annotation_type: AnnotationType;
  content: string;
  suggested_replacement: string | null;
  status: AnnotationStatus;
  resolved_by_id: string | null;
  resolved_at: string | null;
}

export interface ApprovalResponse {
  annotation: Annotation;
  session_approved: boolean;
  approved_sections: SOAPReviewSection[];
}

export interface VersionCreatePayload {
  content: SOAPContent;
  change_summary?: string | null;
  change_type?: ChangeType;
  confidence?: Record<string, number> | null;
}

export interface AnnotationCreatePayload {
  document_version_id: string;
  soap_section: SOAPReviewSection;
  annotation_type: AnnotationType;
  content: string;
  field_path?: string | null;
  text_offset_start?: number | null;
  text_offset_end?: number | null;
  suggested_replacement?: string | null;
}
