import { cn } from "@/lib/utils";

interface ThresholdGaugeProps {
  label: string;
  value: number;
  warnAt: number;
  errorAt: number;
  max?: number;
  unit?: string;
  className?: string;
}

export function ThresholdGauge({ label, value, warnAt, errorAt, max = 100, unit, className }: ThresholdGaugeProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const severity = value >= errorAt ? "error" : value >= warnAt ? "warn" : "ok";
  const colors = {
    ok: "bg-[var(--status-online)]",
    warn: "bg-[var(--status-warning)]",
    error: "bg-[var(--status-error)]",
  } as const;
  return (
    <div className={cn("rounded-lg border border-[var(--border-primary)] p-3", className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="text-[var(--text-muted)]">{label}</span>
        <span className="font-medium text-[var(--text-primary)]">
          {value}
          {unit ?? ""}
        </span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]"
      >
        <div className={cn("h-full transition-all", colors[severity])} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
