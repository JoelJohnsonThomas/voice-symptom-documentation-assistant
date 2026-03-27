import { cn } from "@/lib/utils";
import { type ReactNode, type ButtonHTMLAttributes } from "react";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: "ghost" | "outline" | "solid";
  size?: "sm" | "md" | "lg";
  active?: boolean;
}

const sizeMap = {
  sm: "w-8 h-8",
  md: "w-10 h-10",
  lg: "w-12 h-12",
};

export function IconButton({
  children,
  variant = "ghost",
  size = "md",
  active = false,
  className,
  ...props
}: IconButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-[var(--radius-sm)]",
        "transition-all duration-200 ease-[var(--ease-smooth)]",
        "text-[var(--text-muted)] cursor-pointer",
        sizeMap[size],
        variant === "ghost" && [
          "border-none bg-transparent",
          "hover:bg-[rgba(255,255,255,0.05)] hover:text-[var(--text-primary)]",
        ],
        variant === "outline" && [
          "border border-[var(--border-color)] bg-transparent",
          "hover:border-[var(--border-hover)] hover:text-[var(--text-secondary)]",
        ],
        variant === "solid" && [
          "border-none bg-gradient-to-br from-[var(--violet-600,#7c3aed)] to-[var(--indigo-600,#4f46e5)]",
          "text-white shadow-[var(--shadow-glow-violet)]",
          "hover:shadow-[var(--shadow-glow-violet-lg)]",
        ],
        active && "border-[var(--violet-500)] text-[var(--violet-500)] bg-[rgba(139,92,246,0.08)]",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
