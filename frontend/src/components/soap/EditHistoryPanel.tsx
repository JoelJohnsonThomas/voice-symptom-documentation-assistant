import { Clock, RotateCcw } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import type { EditHistoryEntry } from "../../types/soap";

interface EditHistoryPanelProps {
  history: EditHistoryEntry[];
  onRestore: (index: number) => void;
}

const ACTION_LABELS: Record<EditHistoryEntry["action"], string> = {
  edit: "Edited",
  approve: "Approved",
  reject: "Rejected",
  restore: "Restored",
};

export function EditHistoryPanel({ history, onRestore }: EditHistoryPanelProps) {
  if (history.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-[var(--text-muted)]">
        No edit history
      </p>
    );
  }

  return (
    <div className="max-h-64 space-y-2 overflow-y-auto">
      {history.map((entry, i) => (
        <div
          key={i}
          className="rounded-lg border border-[var(--border-primary)] p-3"
        >
          <div className="mb-1 flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
              <Clock size={12} />
              <span>{new Date(entry.timestamp).toLocaleString()}</span>
              <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-medium">
                {ACTION_LABELS[entry.action]}
              </span>
            </div>
            <button
              onClick={() => onRestore(i)}
              className="flex items-center gap-1 text-xs text-[var(--accent-primary)] hover:underline"
            >
              <RotateCcw size={10} />
              Restore
            </button>
          </div>
          <p className="line-clamp-2 text-xs text-[var(--text-secondary)]">
            {entry.previousContent}
          </p>
        </div>
      ))}
    </div>
  );
}
