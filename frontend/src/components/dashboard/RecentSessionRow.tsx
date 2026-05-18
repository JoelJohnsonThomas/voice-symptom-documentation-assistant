import { ChevronRight, FileText } from "lucide-react";
import { Link } from "react-router-dom";

interface RecentSessionRowProps {
  id: string;
  patientName?: string | null;
  chiefComplaint?: string | null;
  createdAt: string;
}

export function RecentSessionRow({ id, patientName, chiefComplaint, createdAt }: RecentSessionRowProps) {
  return (
    <Link
      to={`/session/${id}`}
      className="flex items-center justify-between rounded-lg border border-[var(--border-primary)] bg-white/[0.02] px-3 py-2 transition-colors hover:bg-white/[0.05]"
    >
      <div className="flex items-center gap-3 overflow-hidden">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
          <FileText size={14} />
        </div>
        <div className="overflow-hidden">
          <p className="truncate text-sm font-medium text-[var(--text-primary)]">
            {patientName ?? "Anonymous patient"}
          </p>
          <p className="truncate text-xs text-[var(--text-muted)]">
            {chiefComplaint ?? "Session " + id.slice(0, 8)}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
        <span>{new Date(createdAt).toLocaleDateString()}</span>
        <ChevronRight size={12} />
      </div>
    </Link>
  );
}
