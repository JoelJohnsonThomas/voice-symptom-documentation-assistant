import { Tag } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import type { ExtractedEntity } from "../../types/conversation";
import { ENTITY_CATEGORY_COLORS } from "../../types/conversation";

interface EntitySidebarProps {
  entities: ExtractedEntity[];
}

export function EntitySidebar({ entities }: EntitySidebarProps) {
  if (entities.length === 0) return null;

  // Group by category
  const grouped = entities.reduce<Record<string, ExtractedEntity[]>>(
    (acc, e) => {
      (acc[e.category] ??= []).push(e);
      return acc;
    },
    {}
  );

  return (
    <GlassCard className="p-4">
      <div className="mb-3 flex items-center gap-2 text-[var(--text-muted)]">
        <Tag size={14} />
        <span className="text-xs font-semibold uppercase tracking-wider">
          Entities
        </span>
        <span className="ml-auto rounded-full bg-[var(--accent-primary)]/20 px-2 py-0.5 text-xs font-bold text-[var(--accent-primary)]">
          {entities.length}
        </span>
      </div>
      <div className="space-y-3">
        {Object.entries(grouped).map(([category, items]) => {
          const colors = ENTITY_CATEGORY_COLORS[category as keyof typeof ENTITY_CATEGORY_COLORS];
          return (
            <div key={category}>
              <p
                className="mb-1 text-xs font-medium capitalize"
                style={{ color: colors?.text }}
              >
                {category.replace("_", " ")}
              </p>
              <div className="flex flex-wrap gap-1">
                {items.map((e, i) => (
                  <span
                    key={i}
                    className="rounded-full px-2 py-0.5 text-xs font-medium"
                    style={{
                      backgroundColor: colors?.bg,
                      color: colors?.text,
                    }}
                  >
                    {e.text}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </GlassCard>
  );
}
