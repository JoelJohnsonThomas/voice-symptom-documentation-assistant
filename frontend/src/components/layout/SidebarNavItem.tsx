import { cn } from "../../lib/utils";
import type { LucideIcon } from "lucide-react";

interface SidebarNavItemProps {
  icon: LucideIcon;
  label: string;
  href: string;
  active?: boolean;
  badge?: string | number;
  collapsed?: boolean;
  onClick?: () => void;
}

export function SidebarNavItem({
  icon: Icon,
  label,
  href,
  active,
  badge,
  collapsed,
  onClick,
}: SidebarNavItemProps) {
  return (
    <a
      href={href}
      onClick={(e) => {
        e.preventDefault();
        onClick?.();
      }}
      className={cn(
        "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
        "hover:bg-white/[0.06] hover:text-[var(--text-primary)]",
        active
          ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] border border-[var(--accent-primary)]/20"
          : "text-[var(--text-secondary)] border border-transparent",
        collapsed && "justify-center px-2"
      )}
      title={collapsed ? label : undefined}
    >
      <Icon
        size={20}
        className={cn(
          "shrink-0 transition-colors",
          active ? "text-[var(--accent-primary)]" : "text-[var(--text-muted)] group-hover:text-[var(--text-secondary)]"
        )}
      />
      {!collapsed && (
        <>
          <span className="truncate">{label}</span>
          {badge !== undefined && (
            <span className="ml-auto rounded-full bg-[var(--accent-primary)]/20 px-2 py-0.5 text-xs font-semibold text-[var(--accent-primary)]">
              {badge}
            </span>
          )}
        </>
      )}
    </a>
  );
}
