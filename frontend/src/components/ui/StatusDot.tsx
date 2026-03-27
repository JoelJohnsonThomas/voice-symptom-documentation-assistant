import { cn } from "@/lib/utils";

type DotStatus = "online" | "offline" | "warning" | "recording";

interface StatusDotProps {
  status?: DotStatus;
  size?: "sm" | "md" | "lg";
  pulse?: boolean;
  className?: string;
}

const statusColors: Record<DotStatus, string> = {
  online: "bg-[var(--emerald-500,#10b981)] shadow-[0_0_8px_rgba(16,185,129,0.4)]",
  offline: "bg-[var(--rose-500,#f43f5e)] shadow-[0_0_8px_rgba(244,63,94,0.4)]",
  warning: "bg-[var(--amber-500,#f59e0b)] shadow-[0_0_8px_rgba(245,158,11,0.4)]",
  recording: "bg-[var(--rose-500,#f43f5e)] shadow-[0_0_12px_rgba(244,63,94,0.5)]",
};

const sizeMap = {
  sm: "w-1.5 h-1.5",
  md: "w-2 h-2",
  lg: "w-3 h-3",
};

export function StatusDot({
  status = "online",
  size = "md",
  pulse = false,
  className,
}: StatusDotProps) {
  return (
    <span
      className={cn(
        "inline-block rounded-full",
        sizeMap[size],
        statusColors[status],
        pulse && "animate-[pulse-dot_2s_ease-in-out_infinite]",
        className
      )}
    />
  );
}
