import { useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Mic,
  Clock,
  Radio,
  Activity,
  Shield,
  Settings,
  Stethoscope,
} from "lucide-react";
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
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo-icon">
          <Stethoscope size={20} color="white" />
        </div>
        <div>
          <div className="logo-text">VoxDoc</div>
          <div className="logo-sub">Clinical Assistant</div>
        </div>
      </div>

      <nav className="sidebar-nav">
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
            onClick={() => navigate(item.href)}
          />
        ))}
      </nav>

      <UserCard />
    </aside>
  );
}
