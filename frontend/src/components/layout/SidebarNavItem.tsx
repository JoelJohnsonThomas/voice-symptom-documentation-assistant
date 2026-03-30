import type { LucideIcon } from "lucide-react";

interface SidebarNavItemProps {
  icon: LucideIcon;
  label: string;
  href: string;
  active?: boolean;
  onClick?: () => void;
}

export function SidebarNavItem({
  icon: Icon,
  label,
  href,
  active,
  onClick,
}: SidebarNavItemProps) {
  return (
    <button
      onClick={onClick}
      className={`nav-item${active ? " active" : ""}`}
      aria-current={active ? "page" : undefined}
    >
      <Icon size={18} />
      <span>{label}</span>
      <span className="nav-dot" />
    </button>
  );
}
