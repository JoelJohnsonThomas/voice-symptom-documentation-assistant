import { useNavigate } from "react-router-dom";
import {
  Mic,
  FileText,
  Clock,
  TrendingUp,
  Activity,
  Plus,
} from "lucide-react";
import { Header } from "../components/layout/Header";
import { StatCard } from "../components/dashboard/StatCard";
import { SystemHealthGrid } from "../components/dashboard/SystemHealthGrid";
import { GlassCard } from "../components/ui/GlassCard";
import { Badge } from "../components/ui/Badge";
import { StatusDot } from "../components/ui/StatusDot";
import type { DashboardStats, SystemHealth, SessionSummary } from "../types/api";
import { useState, useEffect } from "react";

// Mock data — will be replaced by React Query
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

export default function DashboardPage() {
  const navigate = useNavigate();

  return (
    <>
      <Header
        title="Dashboard"
        subtitle="Clinical overview"
        actions={
          <button
            onClick={() => navigate("/session")}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-secondary)] px-4 py-2 text-sm font-medium text-white shadow-lg shadow-[var(--accent-primary)]/20 transition-shadow hover:shadow-[var(--accent-primary)]/40"
          >
            <Plus size={16} />
            New Session
          </button>
        }
      />
      <div className="flex-1 overflow-y-auto p-6">
        {/* Stats row */}
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Total Sessions"
            value={MOCK_STATS.totalSessions.toLocaleString()}
            icon={FileText}
            trend={{ value: 12, label: "vs last month" }}
            glow="violet"
          />
          <StatCard
            label="Today's Sessions"
            value={MOCK_STATS.todaySessions}
            icon={Mic}
            trend={{ value: 8, label: "vs yesterday" }}
            glow="cyan"
          />
          <StatCard
            label="Avg Processing"
            value={`${MOCK_STATS.avgProcessingTime}s`}
            icon={Clock}
            trend={{ value: -15, label: "faster" }}
            glow="emerald"
          />
          <StatCard
            label="Success Rate"
            value={`${MOCK_STATS.successRate}%`}
            icon={TrendingUp}
            trend={{ value: 2, label: "vs last week" }}
            glow="rose"
          />
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Recent sessions */}
          <div className="lg:col-span-2">
            <GlassCard className="p-5">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                  Recent Sessions
                </h3>
                <button
                  onClick={() => navigate("/history")}
                  className="text-xs text-[var(--accent-primary)] hover:underline"
                >
                  View all
                </button>
              </div>
              <div className="space-y-3">
                {MOCK_RECENT.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => navigate(`/session/${session.id}`)}
                    className="flex w-full items-center gap-3 rounded-lg border border-[var(--border-primary)] p-3 text-left transition-colors hover:bg-white/[0.03]"
                  >
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
                      pulse={session.status === "processing" || session.status === "recording"}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                        {session.chiefComplaint}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        {new Date(session.createdAt).toLocaleTimeString()}
                        {session.duration && ` · ${Math.floor(session.duration / 60)}m ${session.duration % 60}s`}
                      </p>
                    </div>
                    <Badge
                      variant={
                        session.status === "completed"
                          ? "success"
                          : session.status === "processing"
                          ? "warning"
                          : "info"
                      }
                    >
                      {session.status}
                    </Badge>
                  </button>
                ))}
              </div>
            </GlassCard>
          </div>

          {/* System health */}
          <SystemHealthGrid health={MOCK_HEALTH} />
        </div>
      </div>
    </>
  );
}
