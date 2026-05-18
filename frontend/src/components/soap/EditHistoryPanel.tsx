import { Clock, RotateCcw } from "lucide-react";
import type { EditHistoryEntry } from "../../types/soap";
import { useVersionList } from "../../hooks/useSoapReview";
import type { VersionSummary } from "../../types/soapReview";

interface EditHistoryPanelProps {
  history?: EditHistoryEntry[];
  onRestore?: (index: number) => void;
  sessionId?: string;
  onSelectVersion?: (version: VersionSummary) => void;
}

const ACTION_LABELS: Record<EditHistoryEntry["action"], string> = {
  edit: "Edited",
  approve: "Approved",
  reject: "Rejected",
  restore: "Restored",
};

const CHANGE_TYPE_LABELS: Record<string, string> = {
  initial: "Initial",
  edit: "Edited",
  ai_generated: "AI generated",
  review: "Reviewed",
  correction: "Corrected",
};

export function EditHistoryPanel({ history, onRestore, sessionId, onSelectVersion }: EditHistoryPanelProps) {
  const versions = useVersionList(sessionId);
  const useRemote = Boolean(sessionId);

  if (useRemote) {
    if (versions.isLoading) {
      return (
        <p className="py-4 text-center text-sm text-[var(--text-muted)]">Loading history…</p>
      );
    }
    if (versions.isError) {
      return (
        <p className="py-4 text-center text-sm text-[var(--status-error)]">Failed to load version history</p>
      );
    }
    const rows = versions.data ?? [];
    if (rows.length === 0) {
      return (
        <p className="py-4 text-center text-sm text-[var(--text-muted)]">No saved versions yet</p>
      );
    }
    return (
      <div className="max-h-64 space-y-2 overflow-y-auto">
        {rows.map((version) => (
          <button
            key={version.id}
            type="button"
            onClick={() => onSelectVersion?.(version)}
            className="w-full rounded-lg border border-[var(--border-primary)] p-3 text-left transition-colors hover:bg-white/[0.04]"
          >
            <div className="mb-1 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
                <Clock size={12} />
                <span>{new Date(version.created_at).toLocaleString()}</span>
                <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-medium">
                  v{version.version_number}
                </span>
                <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-medium">
                  {CHANGE_TYPE_LABELS[version.change_type] ?? version.change_type}
                </span>
              </div>
              <span className="text-[10px] text-[var(--text-muted)]">
                {version.author_username ?? "system"}
              </span>
            </div>
            {version.change_summary && (
              <p className="line-clamp-2 text-xs text-[var(--text-secondary)]">
                {version.change_summary}
              </p>
            )}
          </button>
        ))}
      </div>
    );
  }

  const localHistory = history ?? [];
  if (localHistory.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-[var(--text-muted)]">
        No edit history
      </p>
    );
  }

  return (
    <div className="max-h-64 space-y-2 overflow-y-auto">
      {localHistory.map((entry, i) => (
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
            {onRestore && (
              <button
                onClick={() => onRestore(i)}
                className="flex items-center gap-1 text-xs text-[var(--accent-primary)] hover:underline"
              >
                <RotateCcw size={10} />
                Restore
              </button>
            )}
          </div>
          <p className="line-clamp-2 text-xs text-[var(--text-secondary)]">
            {entry.previousContent}
          </p>
        </div>
      ))}
    </div>
  );
}
