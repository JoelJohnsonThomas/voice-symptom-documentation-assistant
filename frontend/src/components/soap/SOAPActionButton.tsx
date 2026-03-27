import type { LucideIcon } from "lucide-react";
import { cn } from "../../lib/utils";

interface SOAPActionButtonProps {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  variant?: "approve" | "reject" | "edit" | "history" | "default";
  disabled?: boolean;
  size?: "sm" | "md";
}

const VARIANT_STYLES = {
  approve:
    "text-[var(--status-online)] hover:bg-[var(--status-online)]/10 border-[var(--status-online)]/20",
  reject:
    "text-[var(--status-error)] hover:bg-[var(--status-error)]/10 border-[var(--status-error)]/20",
  edit: "text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/10 border-[var(--accent-primary)]/20",
  history:
    "text-[var(--text-muted)] hover:bg-white/[0.06] border-[var(--border-primary)]",
  default:
    "text-[var(--text-secondary)] hover:bg-white/[0.06] border-[var(--border-primary)]",
};

export function SOAPActionButton({
  icon: Icon,
  label,
  onClick,
  variant = "default",
  disabled,
  size = "sm",
}: SOAPActionButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={label}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium transition-colors disabled:opacity-50",
        VARIANT_STYLES[variant],
        size === "md" && "px-3 py-1.5 text-sm"
      )}
    >
      <Icon size={size === "sm" ? 12 : 14} />
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}
