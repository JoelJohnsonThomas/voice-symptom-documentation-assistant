import { useNavigate } from "react-router-dom";
import { Clock, FileText, ChevronRight } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { Badge } from "../ui/Badge";
import { StatusDot } from "../ui/StatusDot";
import type { SessionSummary } from "../../types/api";

interface SessionCardProps {
  session: SessionSummary;
}

export function SessionCard({ session }: SessionCardProps) {
  const navigate = useNavigate();

  return (
    <GlassCard
      hover
      className="cursor-pointer p-4"
      onClick={() => navigate(`/session/${session.id}`)}
    >
      <div className="flex items-start gap-3">
        <StatusDot
          status={
            session.status === "completed"
              ? "online"
              : session.status === "processing"
              ? "warning"
              : session.status === "recording"
              ? "recording"
              : "offline"
          }
          size="sm"
          pulse={session.status === "recording"}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-medium text-[var(--text-primary)]">
              {session.chiefComplaint || "Untitled Session"}
            </p>
            <Badge
              variant={
                session.status === "completed"
                  ? "success"
                  : session.status === "error"
                  ? "error"
                  : session.status === "processing"
                  ? "warning"
                  : "info"
              }
            >
              {session.status}
            </Badge>
          </div>
          <div className="mt-2 flex items-center gap-4 text-xs text-[var(--text-muted)]">
            <span className="flex items-center gap-1">
              <Clock size={12} />
              {new Date(session.createdAt).toLocaleDateString()}
            </span>
            {session.duration && (
              <span className="flex items-center gap-1">
                <FileText size={12} />
                {Math.floor(session.duration / 60)}m {session.duration % 60}s
              </span>
            )}
            {session.language && <span>{session.language.toUpperCase()}</span>}
          </div>
        </div>
        <ChevronRight size={16} className="mt-1 shrink-0 text-[var(--text-muted)]" />
      </div>
    </GlassCard>
  );
}
