import { useNavigate } from "react-router-dom";
import { Mic, FileText, Clock, TrendingUp, Plus } from "lucide-react";
import { Header } from "../components/layout/Header";
import { StatCard } from "../components/dashboard/StatCard";
import { SystemHealthGrid } from "../components/dashboard/SystemHealthGrid";
import type { DashboardStats, SystemHealth, SessionSummary } from "../types/api";

const MOCK_STATS: DashboardStats = {
  totalSessions: 1247,
  activeSessions: 3,
  avgProcessingTime: 2.4,
  successRate: 98.7,
  todaySessions: 24,
  weekSessions: 156,
};

const MOCK_HEALTH: SystemHealth = {
  status: "healthy",
  uptime: 259200,
  cpu: 42,
  memory: 67,
  lastChecked: new Date().toISOString(),
};

const MOCK_RECENT: SessionSummary[] = [
  { id: "1", chiefComplaint: "Chest pain, shortness of breath", status: "completed", createdAt: new Date(Date.now() - 3600000).toISOString(), updatedAt: new Date().toISOString(), duration: 180 },
  { id: "2", chiefComplaint: "Recurring headaches", status: "completed", createdAt: new Date(Date.now() - 7200000).toISOString(), updatedAt: new Date().toISOString(), duration: 120 },
  { id: "3", chiefComplaint: "Lower back pain, radiating to left leg", status: "processing", createdAt: new Date(Date.now() - 1800000).toISOString(), updatedAt: new Date().toISOString() },
];

function statusBadgeClass(status: string) {
  if (status === "completed") return "status-badge success";
  if (status === "processing") return "status-badge warning";
  return "status-badge info";
}

export default function DashboardPage() {
  const navigate = useNavigate();

  return (
    <>
      <Header
        title="Dashboard"
        subtitle="Clinical overview"
        actions={
          <button className="btn-primary" onClick={() => navigate("/session")}>
            <Plus size={16} />
            New Session
          </button>
        }
      />

      {/* Stat cards */}
      <div className="stats-grid">
        <StatCard label="Total Sessions" value={MOCK_STATS.totalSessions.toLocaleString()} icon={FileText} trend={{ value: 12, label: "vs last month" }} glow="violet" />
        <StatCard label="Today's Sessions" value={MOCK_STATS.todaySessions} icon={Mic} trend={{ value: 8, label: "vs yesterday" }} glow="cyan" />
        <StatCard label="Avg Processing" value={`${MOCK_STATS.avgProcessingTime}s`} icon={Clock} trend={{ value: -15, label: "faster" }} glow="emerald" />
        <StatCard label="Success Rate" value={`${MOCK_STATS.successRate}%`} icon={TrendingUp} trend={{ value: 2, label: "vs last week" }} glow="rose" />
      </div>

      {/* System health strip */}
      <div className="health-grid">
        <SystemHealthGrid health={MOCK_HEALTH} />
      </div>

      {/* Recent sessions */}
      <div className="section">
        <div className="section-header">
          <span className="section-title">Recent Sessions</span>
          <button className="section-link" onClick={() => navigate("/history")}>
            View all
          </button>
        </div>
        <div className="recent-list">
          {MOCK_RECENT.map((session) => (
            <button
              key={session.id}
              className="recent-item"
              onClick={() => navigate(`/session/${session.id}`)}
            >
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  flexShrink: 0,
                  background:
                    session.status === "completed"
                      ? "var(--emerald-500)"
                      : session.status === "processing"
                      ? "var(--amber-500)"
                      : "var(--text-muted)",
                  boxShadow:
                    session.status === "completed"
                      ? "0 0 8px rgba(16,185,129,0.4)"
                      : session.status === "processing"
                      ? "0 0 8px rgba(245,158,11,0.4)"
                      : "none",
                }}
              />
              <div className="recent-text">
                <div className="recent-text-main">{session.chiefComplaint}</div>
                <div className="recent-text-sub">
                  {new Date(session.createdAt).toLocaleTimeString()}
                  {session.duration &&
                    ` · ${Math.floor(session.duration / 60)}m ${session.duration % 60}s`}
                </div>
              </div>
              <span className={statusBadgeClass(session.status)}>
                {session.status}
              </span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
