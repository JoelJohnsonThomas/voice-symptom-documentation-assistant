import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  trend?: { value: number; label: string };
  glow?: "violet" | "rose" | "cyan" | "emerald";
}

export function StatCard({ label, value, icon: Icon, trend, glow }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-label">
        <div className={`stat-icon ${glow ?? "violet"}`}>
          <Icon size={16} />
        </div>
        {label}
      </div>
      <div className="stat-value">{value}</div>
      {trend && (
        <div className={`stat-change${trend.value < 0 ? " negative" : ""}`}>
          {trend.value >= 0 ? "↑" : "↓"} {Math.abs(trend.value)}%{" "}
          <span style={{ color: "var(--text-muted)" }}>{trend.label}</span>
        </div>
      )}
    </div>
  );
}
