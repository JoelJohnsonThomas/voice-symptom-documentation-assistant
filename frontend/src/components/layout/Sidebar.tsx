import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Mic,
  Clock,
  Radio,
  Activity,
  Shield,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  Stethoscope,
} from "lucide-react";
import { cn } from "../../lib/utils";
import { SidebarNavItem } from "./SidebarNavItem";
import { UserCard } from "./UserCard";

const NAV_ITEMS = [
  { icon: LayoutDashboard, label: "Dashboard", href: "/" },
  { icon: Mic, label: "Voice Assistant", href: "/session" },
  { icon: Clock, label: "Session History", href: "/history" },
  { icon: Radio, label: "Ambient Mode", href: "/ambient" },
  { icon: Activity, label: "Monitoring", href: "/monitoring" },
  { icon: Shield, label: "HIPAA Compliance", href: "/hipaa" },
  { icon: Settings, label: "Settings", href: "/settings" },
] as const;

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <aside
      className={cn(
        "flex h-screen flex-col border-r border-[var(--border-primary)] bg-[var(--bg-secondary)] transition-all duration-300",
        collapsed ? "w-[68px]" : "w-64"
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 border-b border-[var(--border-primary)] p-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] shadow-lg shadow-[var(--accent-primary)]/20">
          <Stethoscope size={20} className="text-white" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <h1 className="truncate text-sm font-bold text-[var(--text-primary)]">
              Voice Triage
            </h1>
            <p className="text-xs text-[var(--text-muted)]">Clinical Assistant</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {NAV_ITEMS.map((item) => (
          <SidebarNavItem
            key={item.href}
            icon={item.icon}
            label={item.label}
            href={item.href}
            active={
              item.href === "/"
                ? location.pathname === "/"
                : location.pathname.startsWith(item.href)
            }
            collapsed={collapsed}
            onClick={() => navigate(item.href)}
          />
        ))}
      </nav>

      {/* User card */}
      <UserCard collapsed={collapsed} />

      {/* Collapse toggle */}
      <div className="border-t border-[var(--border-primary)] p-3">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex w-full items-center justify-center rounded-lg p-2 text-[var(--text-muted)] transition-colors hover:bg-white/[0.06] hover:text-[var(--text-secondary)]"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>
    </aside>
  );
}
