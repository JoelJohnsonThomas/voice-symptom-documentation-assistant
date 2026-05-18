import { cn } from "@/lib/utils";

interface Entity {
  text: string;
  type?: string;
  code?: string;
}

interface EntityChipGroupProps {
  entities: Entity[];
  className?: string;
  emptyLabel?: string;
}

export function EntityChipGroup({ entities, className, emptyLabel = "No entities" }: EntityChipGroupProps) {
  if (entities.length === 0) {
    return (
      <p className={cn("text-xs italic text-[var(--text-muted)]", className)}>{emptyLabel}</p>
    );
  }
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {entities.map((entity, idx) => (
        <span
          key={`${entity.text}-${idx}`}
          className="inline-flex items-center gap-1 rounded-full border border-[var(--border-primary)] bg-white/[0.04] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]"
        >
          <span className="font-medium text-[var(--text-primary)]">{entity.text}</span>
          {entity.type && (
            <span className="text-[10px] uppercase text-[var(--text-muted)]">{entity.type}</span>
          )}
          {entity.code && (
            <span className="rounded bg-[var(--accent-primary)]/10 px-1 text-[10px] text-[var(--accent-primary)]">
              {entity.code}
            </span>
          )}
        </span>
      ))}
    </div>
  );
}
