import { AlertTriangle, Info, XCircle, AlertOctagon, X } from "lucide-react";
import { cn } from "../../lib/utils";
import type { Alert } from "../../types/api";

interface AlertsListProps {
  alerts: Alert[];
  onDismiss: (id: string) => void;
}

const SEVERITY_CONFIG = {
  info: { icon: Info, color: "text-blue-400", bg: "bg-blue-400/10", border: "border-blue-400/20" },
  warning: { icon: AlertTriangle, color: "text-amber-400", bg: "bg-amber-400/10", border: "border-amber-400/20" },
  error: { icon: XCircle, color: "text-rose-400", bg: "bg-rose-400/10", border: "border-rose-400/20" },
  critical: { icon: AlertOctagon, color: "text-red-500", bg: "bg-red-500/10", border: "border-red-500/20" },
};

export function AlertsList({ alerts, onDismiss }: AlertsListProps) {
  const active = alerts.filter((a) => !a.dismissed);
  if (active.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-[var(--text-muted)]">
        No active alerts
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {active.map((alert) => {
        const config = SEVERITY_CONFIG[alert.severity];
        const Icon = config.icon;
        return (
          <div
            key={alert.id}
            className={cn(
              "flex items-start gap-3 rounded-lg border p-3",
              config.bg,
              config.border
            )}
          >
            <Icon size={16} className={cn("mt-0.5 shrink-0", config.color)} />
            <div className="min-w-0 flex-1">
              <p className={cn("text-sm font-medium", config.color)}>
                {alert.message}
              </p>
              <p className="text-xs text-[var(--text-muted)]">
                {new Date(alert.timestamp).toLocaleString()}
              </p>
            </div>
            <button
              onClick={() => onDismiss(alert.id)}
              className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
