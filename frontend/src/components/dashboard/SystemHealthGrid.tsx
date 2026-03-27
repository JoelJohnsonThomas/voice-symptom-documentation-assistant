import { Cpu, HardDrive, Wifi, Clock } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { StatusDot } from "../ui/StatusDot";
import type { SystemHealth } from "../../types/api";
import { cn } from "../../lib/utils";

interface SystemHealthGridProps {
  health: SystemHealth | null;
}

export function SystemHealthGrid({ health }: SystemHealthGridProps) {
  if (!health) return null;

  const items = [
    {
      icon: Cpu,
      label: "CPU",
      value: `${health.cpu}%`,
      warn: health.cpu > 80,
    },
    {
      icon: HardDrive,
      label: "Memory",
      value: `${health.memory}%`,
      warn: health.memory > 85,
    },
    {
      icon: Wifi,
      label: "Status",
      value: health.status,
      warn: health.status !== "healthy",
    },
    {
      icon: Clock,
      label: "Uptime",
      value: `${Math.floor(health.uptime / 3600)}h`,
      warn: false,
    },
  ];

  return (
    <GlassCard className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          System Health
        </h3>
        <StatusDot
          status={
            health.status === "healthy"
              ? "online"
              : health.status === "degraded"
              ? "warning"
              : "offline"
          }
          size="sm"
          pulse
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        {items.map((item) => (
          <div
            key={item.label}
            className={cn(
              "rounded-lg border border-[var(--border-primary)] p-3",
              item.warn && "border-[var(--status-warning)]/30"
            )}
          >
            <div className="flex items-center gap-2">
              <item.icon
                size={14}
                className={cn(
                  item.warn
                    ? "text-[var(--status-warning)]"
                    : "text-[var(--text-muted)]"
                )}
              />
              <span className="text-xs text-[var(--text-muted)]">
                {item.label}
              </span>
            </div>
            <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
              {item.value}
            </p>
          </div>
        ))}
      </div>
    </GlassCard>
  );
}
