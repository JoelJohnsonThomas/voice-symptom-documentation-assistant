import { useState } from "react";
import { MessageSquarePlus } from "lucide-react";
import { Drawer } from "../ui/Drawer";
import { AnnotationItem } from "./AnnotationItem";
import {
  useAnnotationList,
  useCreateAnnotation,
  useUpdateAnnotationStatus,
} from "../../hooks/useSoapReview";
import type {
  AnnotationStatus,
  AnnotationType,
  SOAPReviewSection,
} from "../../types/soapReview";

const SECTIONS: SOAPReviewSection[] = ["subjective", "objective", "assessment", "plan"];
const TYPES: AnnotationType[] = ["correction", "addition", "question", "flag"];
const STATUSES: { label: string; value: AnnotationStatus | "all" }[] = [
  { label: "Open", value: "open" },
  { label: "Resolved", value: "resolved" },
  { label: "All", value: "all" },
];

interface AnnotationDrawerProps {
  open: boolean;
  onClose: () => void;
  sessionId: string;
  currentVersionId: string | null | undefined;
}

export function AnnotationDrawer({ open, onClose, sessionId, currentVersionId }: AnnotationDrawerProps) {
  const [statusFilter, setStatusFilter] = useState<AnnotationStatus | "all">("open");
  const [draftSection, setDraftSection] = useState<SOAPReviewSection>("subjective");
  const [draftType, setDraftType] = useState<AnnotationType>("correction");
  const [draftContent, setDraftContent] = useState("");

  const annotations = useAnnotationList(sessionId, {
    annotation_status: statusFilter === "all" ? undefined : statusFilter,
  });
  const createMutation = useCreateAnnotation(sessionId);
  const updateMutation = useUpdateAnnotationStatus(sessionId);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentVersionId || !draftContent.trim()) return;
    createMutation.mutate(
      {
        document_version_id: currentVersionId,
        soap_section: draftSection,
        annotation_type: draftType,
        content: draftContent.trim(),
      },
      {
        onSuccess: () => setDraftContent(""),
      },
    );
  };

  const handleResolve = (id: string) => updateMutation.mutate({ id, status: "resolved" });
  const handleReject = (id: string) => updateMutation.mutate({ id, status: "rejected" });

  return (
    <Drawer open={open} onClose={onClose} title="Clinician Annotations">
      <div className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-2 rounded-lg border border-[var(--border-primary)] bg-white/[0.03] p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)]">
            <MessageSquarePlus size={14} />
            New annotation
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-[var(--text-muted)]">
              Section
              <select
                value={draftSection}
                onChange={(e) => setDraftSection(e.target.value as SOAPReviewSection)}
                className="mt-1 w-full rounded border border-[var(--border-primary)] bg-[var(--bg-card)] px-2 py-1 text-sm"
              >
                {SECTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-[var(--text-muted)]">
              Type
              <select
                value={draftType}
                onChange={(e) => setDraftType(e.target.value as AnnotationType)}
                className="mt-1 w-full rounded border border-[var(--border-primary)] bg-[var(--bg-card)] px-2 py-1 text-sm"
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <textarea
            value={draftContent}
            onChange={(e) => setDraftContent(e.target.value)}
            placeholder="Describe the correction, question, or flag…"
            rows={3}
            className="w-full rounded border border-[var(--border-primary)] bg-[var(--bg-card)] px-2 py-1 text-sm"
            maxLength={4000}
          />
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
            <span>{draftContent.length}/4000</span>
            <button
              type="submit"
              disabled={!currentVersionId || !draftContent.trim() || createMutation.isPending}
              className="rounded bg-[var(--accent-primary)] px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              {createMutation.isPending ? "Saving…" : "Post annotation"}
            </button>
          </div>
          {!currentVersionId && (
            <p className="text-[10px] text-[var(--status-warning)]">
              Save a SOAP version first to attach annotations.
            </p>
          )}
        </form>

        <div className="flex gap-1 rounded-md border border-[var(--border-primary)] bg-white/[0.02] p-1 text-xs">
          {STATUSES.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => setStatusFilter(s.value)}
              className={
                "flex-1 rounded px-2 py-1 transition-colors " +
                (statusFilter === s.value
                  ? "bg-[var(--accent-primary)]/15 text-[var(--accent-primary)]"
                  : "text-[var(--text-muted)] hover:bg-white/[0.04]")
              }
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="space-y-2">
          {annotations.isLoading && (
            <p className="text-center text-xs text-[var(--text-muted)]">Loading…</p>
          )}
          {annotations.isError && (
            <p className="text-center text-xs text-[var(--status-error)]">Failed to load annotations</p>
          )}
          {annotations.data?.length === 0 && (
            <p className="text-center text-xs text-[var(--text-muted)]">No annotations</p>
          )}
          {annotations.data?.map((a) => (
            <AnnotationItem
              key={a.id}
              annotation={a}
              onResolve={handleResolve}
              onReject={handleReject}
              disabled={updateMutation.isPending}
            />
          ))}
        </div>
      </div>
    </Drawer>
  );
}
