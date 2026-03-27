import { cn } from "@/lib/utils";

interface DividerProps {
  label?: string;
  className?: string;
}

export function Divider({ label, className }: DividerProps) {
  if (!label) {
    return <div className={cn("h-px bg-[var(--border-color)]", className)} />;
  }

  return (
    <div className={cn("flex items-center", className)}>
      <div className="flex-1 h-px bg-[var(--border-color)]" />
      <span className="px-4 text-[0.7rem] font-semibold tracking-widest text-[var(--text-muted)] uppercase">
        {label}
      </span>
      <div className="flex-1 h-px bg-[var(--border-color)]" />
    </div>
  );
}
