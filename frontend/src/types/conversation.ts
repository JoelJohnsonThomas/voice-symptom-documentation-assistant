export type ConversationMode = "patient" | "clinician";

export type MessageRole = "user" | "assistant" | "system";

export interface ConversationMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  isEmergency?: boolean;
  entities?: ExtractedEntity[];
}

export interface ExtractedEntity {
  text: string;
  category: EntityCategory;
  confidence: number;
}

export type EntityCategory =
  | "symptom"
  | "condition"
  | "medication"
  | "duration"
  | "severity"
  | "body_part"
  | "procedure"
  | "vital_sign";

export const ENTITY_CATEGORY_COLORS: Record<EntityCategory, { bg: string; text: string }> = {
  symptom: { bg: "rgba(244, 63, 94, 0.15)", text: "var(--rose-500, #f43f5e)" },
  condition: { bg: "rgba(139, 92, 246, 0.15)", text: "var(--violet-500, #8b5cf6)" },
  medication: { bg: "rgba(6, 182, 212, 0.15)", text: "var(--cyan-500, #06b6d4)" },
  duration: { bg: "rgba(99, 102, 241, 0.15)", text: "var(--indigo-500, #6366f1)" },
  severity: { bg: "rgba(245, 158, 11, 0.15)", text: "var(--amber-500, #f59e0b)" },
  body_part: { bg: "rgba(16, 185, 129, 0.15)", text: "var(--emerald-500, #10b981)" },
  procedure: { bg: "rgba(59, 130, 246, 0.15)", text: "var(--blue-500, #3b82f6)" },
  vital_sign: { bg: "rgba(168, 85, 247, 0.15)", text: "var(--purple-500, #a855f7)" },
};
