import { Check, MessageSquare, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Annotation } from "../../types/soapReview";

const TYPE_LABELS: Record<Annotation["annotation_type"], string> = {
  correction: "Correction",
  addition: "Addition",
  question: "Question",
  approval: "Approval",
  flag: "Flag",
};

const STATUS_STYLES: Record<Annotation["status"], string> = {
  open: "bg-[var(--status-warning)]/10 text-[var(--status-warning)]",
  resolved: "bg-[var(--status-online)]/10 text-[var(--status-online)]",
  rejected: "bg-[var(--status-error)]/10 text-[var(--status-error)]",
};

interface AnnotationItemProps {
  annotation: Annotation;
  onResolve?: (id: string) => void;
  onReject?: (id: string) => void;
  disabled?: boolean;
}

export function AnnotationItem({ annotation, onResolve, onReject, disabled }: AnnotationItemProps) {
  const showActions = annotation.status === "open" && (onResolve || onReject);
  return (
    <div className="rounded-lg border border-[var(--border-primary)] bg-white/[0.02] p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <MessageSquare size={12} />
          <span className="font-medium text-[var(--text-secondary)]">
            {TYPE_LABELS[annotation.annotation_type]}
          </span>
          <span className="rounded bg-white/[0.06] px-1.5 py-0.5 uppercase">
            {annotation.soap_section}
          </span>
        </div>
        <span className={cn("rounded px-2 py-0.5 text-[10px] uppercase tracking-wide", STATUS_STYLES[annotation.status])}>
          {annotation.status}
        </span>
      </div>
      <p className="text-sm text-[var(--text-primary)]">{annotation.content}</p>
      {annotation.suggested_replacement && (
        <p className="mt-2 rounded bg-[var(--accent-primary)]/10 p-2 text-xs text-[var(--accent-primary)]">
          Suggest: {annotation.suggested_replacement}
        </p>
      )}
      <div className="mt-2 flex items-center justify-between">
        <span className="text-[10px] text-[var(--text-muted)]">
          {annotation.author_username ?? "unknown"} · {new Date(annotation.created_at).toLocaleString()}
        </span>
        {showActions && (
          <div className="flex gap-1">
            {onResolve && (
              <button
                type="button"
                onClick={() => onResolve(annotation.id)}
                disabled={disabled}
                className="inline-flex items-center gap-1 rounded border border-[var(--status-online)]/20 px-2 py-0.5 text-[10px] text-[var(--status-online)] hover:bg-[var(--status-online)]/10 disabled:opacity-50"
              >
                <Check size={10} /> Resolve
              </button>
            )}
            {onReject && (
              <button
                type="button"
                onClick={() => onReject(annotation.id)}
                disabled={disabled}
                className="inline-flex items-center gap-1 rounded border border-[var(--status-error)]/20 px-2 py-0.5 text-[10px] text-[var(--status-error)] hover:bg-[var(--status-error)]/10 disabled:opacity-50"
              >
                <X size={10} /> Reject
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
