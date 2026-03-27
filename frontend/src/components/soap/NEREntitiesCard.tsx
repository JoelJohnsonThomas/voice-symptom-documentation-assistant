import { Tag } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { ConfidencePill } from "../ui/ConfidencePill";
import type { NEREntities } from "../../types/api";

interface NEREntitiesCardProps {
  entities: NEREntities;
}

const CATEGORY_COLORS: Record<string, { bg: string; text: string }> = {
  conditions: { bg: "rgba(244,63,94,0.15)", text: "#f43f5e" },
  medications: { bg: "rgba(6,182,212,0.15)", text: "#06b6d4" },
  procedures: { bg: "rgba(59,130,246,0.15)", text: "#3b82f6" },
  anatomical: { bg: "rgba(16,185,129,0.15)", text: "#10b981" },
};

export function NEREntitiesCard({ entities }: NEREntitiesCardProps) {
  const sections = [
    { key: "conditions", label: "Conditions", items: entities.conditions },
    { key: "medications", label: "Medications", items: entities.medications },
    { key: "procedures", label: "Procedures", items: entities.procedures || [] },
    { key: "anatomical", label: "Anatomical", items: entities.anatomical || [] },
  ].filter((s) => s.items.length > 0);

  if (sections.length === 0) return null;

  return (
    <GlassCard className="p-5">
      <div className="mb-3 flex items-center gap-2 text-[var(--text-muted)]">
        <Tag size={14} />
        <span className="text-xs font-semibold uppercase tracking-wider">
          Extracted Entities
        </span>
      </div>
      <div className="space-y-3">
        {sections.map((section) => (
          <div key={section.key}>
            <p className="mb-1.5 text-xs font-medium text-[var(--text-muted)]">
              {section.label}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {section.items.map((item, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium"
                  style={{
                    backgroundColor: CATEGORY_COLORS[section.key]?.bg,
                    color: CATEGORY_COLORS[section.key]?.text,
                  }}
                >
                  {item.text}
                  {item.umlsCode && (
                    <span className="opacity-60">[{item.umlsCode}]</span>
                  )}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  );
}
