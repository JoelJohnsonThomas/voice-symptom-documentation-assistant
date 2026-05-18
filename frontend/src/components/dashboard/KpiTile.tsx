import type { LucideIcon } from "lucide-react";
import { TrendingDown, TrendingUp } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { cn } from "@/lib/utils";

interface KpiTileProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  delta?: number;
  glow?: "violet" | "rose" | "cyan" | "emerald";
  className?: string;
}

export function KpiTile({ icon: Icon, label, value, delta, glow, className }: KpiTileProps) {
  const positive = typeof delta === "number" && delta >= 0;
  return (
    <GlassCard glow={glow} className={cn("p-4", className)}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-[var(--text-muted)]">{label}</p>
          <p className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">{value}</p>
        </div>
        <div className="rounded-md bg-white/[0.04] p-2 text-[var(--accent-primary)]">
          <Icon size={16} />
        </div>
      </div>
      {typeof delta === "number" && (
        <p
          className={cn(
            "mt-2 inline-flex items-center gap-1 text-[10px] font-medium",
            positive ? "text-[var(--status-online)]" : "text-[var(--status-error)]",
          )}
        >
          {positive ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
          {Math.abs(delta).toFixed(1)}%
        </p>
      )}
    </GlassCard>
  );
}
