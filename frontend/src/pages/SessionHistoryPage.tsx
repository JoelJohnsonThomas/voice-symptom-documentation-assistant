import { useState } from "react";
import { Search, Filter, Download } from "lucide-react";
import { Header } from "../components/layout/Header";
import { SessionCard } from "../components/session/SessionCard";
import { IconButton } from "../components/ui/IconButton";
import type { SessionSummary } from "../types/api";

const COMPLAINTS = [
  "Chest pain, shortness of breath",
  "Recurring headaches with visual aura",
  "Lower back pain, radiating to left leg",
  "Persistent cough, fever for 3 days",
  "Abdominal pain, nausea",
  "Dizziness and lightheadedness",
  "Skin rash on forearms",
  "Joint pain and swelling",
  "Difficulty sleeping, anxiety",
  "Sore throat, difficulty swallowing",
  "Eye redness and discharge",
  "Numbness in right hand",
] as const;

const STATUSES: SessionSummary["status"][] = [
  "completed", "completed", "completed", "processing", "completed", "error",
  "completed", "completed", "completed", "completed", "completed", "completed",
];

const MOCK_SESSIONS: SessionSummary[] = Array.from({ length: 12 }, (_, i) => ({
  id: `session-${i + 1}`,
  chiefComplaint: COMPLAINTS[i] ?? "General consultation",
  status: STATUSES[i] ?? "completed",
  createdAt: new Date(Date.now() - i * 3600000 * 4).toISOString(),
  updatedAt: new Date(Date.now() - i * 3600000 * 3).toISOString(),
  duration: 90 + Math.floor(Math.random() * 180),
  language: "en",
}));

export default function SessionHistoryPage() {
  const [search, setSearch] = useState("");

  const filtered = MOCK_SESSIONS.filter((s) =>
    s.chiefComplaint.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <Header
        title="Session History"
        subtitle={`${MOCK_SESSIONS.length} total encounters`}
        actions={
          <IconButton variant="outline" aria-label="Export all">
            <Download size={16} />
          </IconButton>
        }
      />
      <div className="flex-1 overflow-y-auto p-6">
        {/* Search bar */}
        <div className="mb-6 flex gap-3">
          <div className="relative flex-1">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search sessions..."
              className="w-full rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] py-2.5 pl-10 pr-4 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[var(--accent-primary)]"
            />
          </div>
          <IconButton variant="outline" aria-label="Filter">
            <Filter size={16} />
          </IconButton>
        </div>

        {/* Session list */}
        <div className="space-y-3">
          {filtered.map((session) => (
            <SessionCard key={session.id} session={session} />
          ))}
          {filtered.length === 0 && (
            <p className="py-12 text-center text-sm text-[var(--text-muted)]">
              No sessions found
            </p>
          )}
        </div>
      </div>
    </>
  );
}
