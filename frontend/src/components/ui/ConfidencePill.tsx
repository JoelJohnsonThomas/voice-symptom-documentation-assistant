import { cn } from "@/lib/utils";

type ConfidenceLevel = "high" | "medium" | "low";

interface ConfidencePillProps {
  level: ConfidenceLevel;
  label?: string;
  className?: string;
}

const levelStyles: Record<ConfidenceLevel, string> = {
  high: "bg-[rgba(16,185,129,0.15)] text-[var(--emerald-500,#10b981)]",
  medium: "bg-[rgba(245,158,11,0.15)] text-[var(--amber-500,#f59e0b)]",
  low: "bg-[rgba(244,63,94,0.15)] text-[var(--rose-500,#f43f5e)]",
};

const defaultLabels: Record<ConfidenceLevel, string> = {
  high: "High confidence",
  medium: "Verify",
  low: "Needs verification",
};

export function ConfidencePill({ level, label, className }: ConfidencePillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full",
        "text-[0.7rem] font-semibold",
        levelStyles[level],
        className
      )}
    >
      {label ?? defaultLabels[level]}
    </span>
  );
}
