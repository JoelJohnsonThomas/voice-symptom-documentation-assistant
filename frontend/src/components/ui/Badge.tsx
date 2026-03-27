import { cn } from "@/lib/utils";
import { type ReactNode } from "react";

type BadgeVariant = "info" | "success" | "warning" | "error" | "neutral";

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  info: "bg-[rgba(99,102,241,0.15)] text-[var(--indigo-500,#6366f1)] border-[rgba(99,102,241,0.2)]",
  success: "bg-[rgba(16,185,129,0.15)] text-[var(--emerald-500,#10b981)] border-[rgba(16,185,129,0.2)]",
  warning: "bg-[rgba(245,158,11,0.15)] text-[var(--amber-500,#f59e0b)] border-[rgba(245,158,11,0.2)]",
  error: "bg-[rgba(244,63,94,0.15)] text-[var(--rose-500,#f43f5e)] border-[rgba(244,63,94,0.2)]",
  neutral: "bg-[rgba(148,163,184,0.1)] text-[var(--text-muted)] border-[var(--border-color)]",
};

export function Badge({ children, variant = "neutral", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full",
        "text-[0.7rem] font-semibold border",
        variantStyles[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
