import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  glow?: "violet" | "rose" | "cyan" | "emerald" | false;
  hover?: boolean;
  onClick?: () => void;
}

export function GlassCard({
  children,
  className,
  glow = false,
  hover = false,
  onClick,
}: GlassCardProps) {
  const glowStyles = {
    violet: "shadow-[0_8px_24px_rgba(139,92,246,0.15)]",
    rose: "shadow-[0_8px_24px_rgba(244,63,94,0.15)]",
    cyan: "shadow-[0_8px_24px_rgba(6,182,212,0.15)]",
    emerald: "shadow-[0_8px_24px_rgba(16,185,129,0.15)]",
  };

  return (
    <div
      onClick={onClick}
      className={cn(
        "rounded-[var(--radius-lg)] border border-[var(--border-color)] bg-[var(--bg-card)]",
        "transition-all duration-300 ease-[var(--ease-smooth)]",
        hover && "cursor-pointer hover:border-[var(--border-hover)] hover:-translate-y-0.5",
        glow && glowStyles[glow],
        onClick && "cursor-pointer",
        className
      )}
    >
      {children}
    </div>
  );
}
