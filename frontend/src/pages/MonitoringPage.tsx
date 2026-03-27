import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { Header } from "../components/layout/Header";
import { ModelStatusCard } from "../components/monitoring/ModelStatusCard";
import { QueueCard } from "../components/monitoring/QueueCard";
import { AlertsList } from "../components/monitoring/AlertsList";
import { GlassCard } from "../components/ui/GlassCard";
import { IconButton } from "../components/ui/IconButton";
import type { MonitoringData } from "../types/api";

const MOCK_DATA: MonitoringData = {
  models: [
    { name: "Whisper Large v3", status: "online", requestCount: 4521, errorRate: 0.12, avgLatency: 820, p95Latency: 1450 },
    { name: "Med-PaLM 2", status: "online", requestCount: 3892, errorRate: 0.08, avgLatency: 1200, p95Latency: 2100 },
    { name: "BioBERT NER", status: "degraded", requestCount: 4521, errorRate: 2.3, avgLatency: 45, p95Latency: 120 },
    { name: "Voice Biometrics", status: "online", requestCount: 1205, errorRate: 0.5, avgLatency: 150, p95Latency: 300 },
  ],
  queue: { active: 3, queued: 7, maxConcurrent: 10, avgProcessingTime: 2400 },
  connections: { http: 42, websocket: 8 },
  alerts: [
    { id: "1", severity: "warning", message: "BioBERT NER latency above threshold (>100ms avg)", timestamp: new Date().toISOString() },
    { id: "2", severity: "info", message: "Scheduled maintenance window in 4 hours", timestamp: new Date().toISOString() },
  ],
  uptime: 259200,
  lastRefresh: new Date().toISOString(),
};

export default function MonitoringPage() {
  const [alerts, setAlerts] = useState(MOCK_DATA.alerts);

  const dismissAlert = (id: string) => {
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, dismissed: true } : a))
    );
  };

  return (
    <>
      <Header
        title="System Monitoring"
        subtitle="Performance & health"
        actions={
          <IconButton variant="outline" aria-label="Refresh">
            <RefreshCw size={16} />
          </IconButton>
        }
      />
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-6xl space-y-6">
          {/* Connection stats */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <GlassCard className="p-4 text-center">
              <p className="text-xs text-[var(--text-muted)]">HTTP Connections</p>
              <p className="text-2xl font-bold text-[var(--text-primary)]">{MOCK_DATA.connections.http}</p>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <p className="text-xs text-[var(--text-muted)]">WebSocket</p>
              <p className="text-2xl font-bold text-[var(--text-primary)]">{MOCK_DATA.connections.websocket}</p>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <p className="text-xs text-[var(--text-muted)]">Uptime</p>
              <p className="text-2xl font-bold text-[var(--text-primary)]">{Math.floor(MOCK_DATA.uptime / 3600)}h</p>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <p className="text-xs text-[var(--text-muted)]">Avg Processing</p>
              <p className="text-2xl font-bold text-[var(--text-primary)]">{(MOCK_DATA.queue.avgProcessingTime / 1000).toFixed(1)}s</p>
            </GlassCard>
          </div>

          {/* Models */}
          <div>
            <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Model Performance</h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {MOCK_DATA.models.map((model) => (
                <ModelStatusCard key={model.name} model={model} />
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <QueueCard queue={MOCK_DATA.queue} />
            <GlassCard className="p-5">
              <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Alerts</h3>
              <AlertsList alerts={alerts} onDismiss={dismissAlert} />
            </GlassCard>
          </div>
        </div>
      </div>
    </>
  );
}
