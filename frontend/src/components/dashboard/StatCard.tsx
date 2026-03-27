import type { LucideIcon } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { cn } from "../../lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  trend?: { value: number; label: string };
  glow?: "violet" | "rose" | "cyan" | "emerald";
}

export function StatCard({ label, value, icon: Icon, trend, glow }: StatCardProps) {
  return (
    <GlassCard glow={glow} className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-[var(--text-muted)]">{label}</p>
          <p className="mt-1 text-2xl font-bold text-[var(--text-primary)]">
            {value}
          </p>
          {trend && (
            <p
              className={cn(
                "mt-1 text-xs font-medium",
                trend.value >= 0
                  ? "text-[var(--status-online)]"
                  : "text-[var(--status-error)]"
              )}
            >
              {trend.value >= 0 ? "↑" : "↓"} {Math.abs(trend.value)}%{" "}
              <span className="text-[var(--text-muted)]">{trend.label}</span>
            </p>
          )}
        </div>
        <div className="rounded-lg bg-[var(--accent-primary)]/10 p-2.5">
          <Icon size={20} className="text-[var(--accent-primary)]" />
        </div>
      </div>
    </GlassCard>
  );
}
