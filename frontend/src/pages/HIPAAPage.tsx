import { Shield, Lock, FileCheck, Clock, AlertTriangle, CheckCircle } from "lucide-react";
import { Header } from "../components/layout/Header";
import { GlassCard } from "../components/ui/GlassCard";
import { StatCard } from "../components/dashboard/StatCard";
import { Badge } from "../components/ui/Badge";

const MOCK_AUDIT: { action: string; user: string; time: string; ip: string }[] = [
  { action: "Session created", user: "Dr. Smith", time: "2 min ago", ip: "10.0.1.42" },
  { action: "SOAP note approved", user: "Dr. Smith", time: "5 min ago", ip: "10.0.1.42" },
  { action: "EHR push completed", user: "System", time: "8 min ago", ip: "10.0.1.1" },
  { action: "User login", user: "Dr. Johnson", time: "15 min ago", ip: "10.0.2.18" },
  { action: "Export PDF", user: "Dr. Smith", time: "22 min ago", ip: "10.0.1.42" },
];

export default function HIPAAPage() {
  return (
    <>
      <Header title="HIPAA Compliance" subtitle="Security & audit trail" />
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-6xl space-y-6">
          {/* Stats */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Compliance Score"
              value="96%"
              icon={Shield}
              glow="emerald"
            />
            <StatCard
              label="Encryption"
              value="AES-256"
              icon={Lock}
              glow="violet"
            />
            <StatCard
              label="Audit Entries"
              value="12,847"
              icon={FileCheck}
              glow="cyan"
            />
            <StatCard
              label="Retention"
              value="7 years"
              icon={Clock}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Compliance checklist */}
            <GlassCard className="p-5">
              <h3 className="mb-4 text-sm font-semibold text-[var(--text-primary)]">
                Compliance Status
              </h3>
              <div className="space-y-3">
                {[
                  { label: "Data encryption at rest", status: true },
                  { label: "Data encryption in transit", status: true },
                  { label: "Access control (RBAC)", status: true },
                  { label: "Audit trail logging", status: true },
                  { label: "PHI de-identification", status: true },
                  { label: "BAA documentation", status: true },
                  { label: "Incident response plan", status: false },
                  { label: "Annual risk assessment", status: true },
                ].map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center justify-between rounded-lg border border-[var(--border-primary)] p-3"
                  >
                    <span className="text-sm text-[var(--text-secondary)]">
                      {item.label}
                    </span>
                    {item.status ? (
                      <Badge variant="success">
                        <CheckCircle size={10} className="mr-1" />
                        Active
                      </Badge>
                    ) : (
                      <Badge variant="warning">
                        <AlertTriangle size={10} className="mr-1" />
                        Pending
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            </GlassCard>

            {/* Audit log */}
            <GlassCard className="p-5">
              <h3 className="mb-4 text-sm font-semibold text-[var(--text-primary)]">
                Recent Audit Trail
              </h3>
              <div className="space-y-2">
                {MOCK_AUDIT.map((entry, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 rounded-lg border border-[var(--border-primary)] p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-[var(--text-primary)]">
                        {entry.action}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        {entry.user} · {entry.ip}
                      </p>
                    </div>
                    <span className="shrink-0 text-xs text-[var(--text-muted)]">
                      {entry.time}
                    </span>
                  </div>
                ))}
              </div>
            </GlassCard>
          </div>
        </div>
      </div>
    </>
  );
}
