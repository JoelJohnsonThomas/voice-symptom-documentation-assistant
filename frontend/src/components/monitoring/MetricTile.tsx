import { GlassCard } from "../ui/GlassCard";
import { cn } from "@/lib/utils";

interface MetricTileProps {
  label: string;
  value: string;
  unit?: string;
  trend?: "up" | "down" | "flat";
  severity?: "ok" | "warn" | "error";
  className?: string;
}

const SEVERITY_CLASSES: Record<NonNullable<MetricTileProps["severity"]>, string> = {
  ok: "text-[var(--status-online)]",
  warn: "text-[var(--status-warning)]",
  error: "text-[var(--status-error)]",
};

export function MetricTile({ label, value, unit, trend, severity = "ok", className }: MetricTileProps) {
  const trendSymbol = trend === "up" ? "↑" : trend === "down" ? "↓" : trend === "flat" ? "→" : "";
  return (
    <GlassCard className={cn("p-3", className)}>
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p className={cn("mt-1 text-xl font-semibold", SEVERITY_CLASSES[severity])}>
        {value}
        {unit && <span className="ml-0.5 text-xs">{unit}</span>}
        {trendSymbol && <span className="ml-1 text-xs">{trendSymbol}</span>}
      </p>
    </GlassCard>
  );
}
