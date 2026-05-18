import { type ReactNode, useState } from "react";
import { cn } from "@/lib/utils";

interface TooltipProps {
  label: string;
  children: ReactNode;
  side?: "top" | "bottom";
  className?: string;
}

export function Tooltip({ label, children, side = "top", className }: TooltipProps) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open && (
        <span
          role="tooltip"
          className={cn(
            "pointer-events-none absolute left-1/2 z-50 -translate-x-1/2 whitespace-nowrap rounded-md border border-[var(--border-primary)] bg-[var(--bg-card)] px-2 py-1 text-[10px] text-[var(--text-primary)] shadow-lg",
            side === "top" ? "bottom-full mb-1" : "top-full mt-1",
            className,
          )}
        >
          {label}
        </span>
      )}
    </span>
  );
}
