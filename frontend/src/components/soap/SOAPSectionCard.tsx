import { useState } from "react";
import { Check, X, Edit3, Clock } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { SOAPActionButton } from "./SOAPActionButton";
import { EditHistoryPanel } from "./EditHistoryPanel";
import { ConfidencePill } from "../ui/ConfidencePill";
import { cn } from "../../lib/utils";
import { SOAP_SECTION_META, type SOAPSectionKey, type SOAPSectionState } from "../../types/soap";

interface SOAPSectionCardProps {
  sectionKey: SOAPSectionKey;
  state: SOAPSectionState;
  confidence?: number;
  onApprove: () => void;
  onReject: () => void;
  onEdit: (content: string) => void;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onRestore: (index: number) => void;
}

export function SOAPSectionCard({
  sectionKey,
  state,
  confidence,
  onApprove,
  onReject,
  onEdit,
  onStartEdit,
  onCancelEdit,
  onRestore,
}: SOAPSectionCardProps) {
  const meta = SOAP_SECTION_META[sectionKey];
  const [editValue, setEditValue] = useState(state.content);
  const [showHistory, setShowHistory] = useState(false);

  const handleSaveEdit = () => {
    onEdit(editValue);
  };

  return (
    <GlassCard
      className={cn(
        "relative overflow-hidden p-5",
        state.status === "approved" && "border-[var(--status-online)]/30",
        state.status === "rejected" && "border-[var(--status-error)]/30"
      )}
    >
      {/* Colored left border accent */}
      <div
        className="absolute left-0 top-0 h-full w-1"
        style={{ backgroundColor: meta.color }}
      />

      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="rounded px-2 py-0.5 text-xs font-bold"
            style={{ backgroundColor: meta.bgColor, color: meta.color }}
          >
            {meta.shortLabel}
          </span>
          <span className="text-sm font-medium text-[var(--text-primary)]">
            {meta.label}
          </span>
          {confidence !== undefined && (
            <ConfidencePill level={confidence >= 0.8 ? "high" : confidence >= 0.5 ? "medium" : "low"} />
          )}
        </div>
        <div className="flex items-center gap-1">
          {state.status === "pending" && (
            <>
              <SOAPActionButton
                icon={Check}
                label="Approve"
                variant="approve"
                onClick={onApprove}
              />
              <SOAPActionButton
                icon={X}
                label="Reject"
                variant="reject"
                onClick={onReject}
              />
              <SOAPActionButton
                icon={Edit3}
                label="Edit"
                variant="edit"
                onClick={onStartEdit}
              />
            </>
          )}
          {state.editHistory.length > 0 && (
            <SOAPActionButton
              icon={Clock}
              label="History"
              variant="history"
              onClick={() => setShowHistory(!showHistory)}
            />
          )}
        </div>
      </div>

      {/* Content */}
      {state.isEditing ? (
        <div className="space-y-2">
          <textarea
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            rows={4}
            className="w-full rounded-lg border border-[var(--accent-primary)]/30 bg-[var(--bg-primary)]/50 p-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)]"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSaveEdit}
              className="rounded-md bg-[var(--accent-primary)] px-3 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-primary)]/80"
            >
              Save
            </button>
            <button
              onClick={onCancelEdit}
              className="rounded-md border border-[var(--border-primary)] px-3 py-1.5 text-xs text-[var(--text-muted)] hover:bg-white/[0.06]"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-secondary)]">
          {state.content || (
            <span className="italic text-[var(--text-muted)]">
              No content generated
            </span>
          )}
        </p>
      )}

      {/* Status badge */}
      {state.status !== "pending" && (
        <div
          className={cn(
            "mt-3 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
            state.status === "approved"
              ? "bg-[var(--status-online)]/10 text-[var(--status-online)]"
              : "bg-[var(--status-error)]/10 text-[var(--status-error)]"
          )}
        >
          {state.status === "approved" ? (
            <Check size={10} />
          ) : (
            <X size={10} />
          )}
          {state.status === "approved" ? "Approved" : "Rejected"}
        </div>
      )}

      {/* Edit history panel */}
      {showHistory && (
        <div className="mt-3 border-t border-[var(--border-primary)] pt-3">
          <EditHistoryPanel
            history={state.editHistory}
            onRestore={onRestore}
          />
        </div>
      )}
    </GlassCard>
  );
}
