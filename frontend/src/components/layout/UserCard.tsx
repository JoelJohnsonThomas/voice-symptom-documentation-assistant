import { LogOut } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../../hooks/useAuth";

export function UserCard() {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!user) return null;

  const initials = user.name
    .split(" ")
    .map((n: string) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="sidebar-footer">
      <div className="user-card" style={{ position: "relative" }}>
        <button
          className="user-avatar"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="User menu"
        >
          {initials}
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="user-name">{user.name}</div>
          <div className="user-role">{user.role}</div>
        </div>
        <button
          onClick={() => logout()}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            display: "flex",
            alignItems: "center",
            padding: "4px",
          }}
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut size={16} />
        </button>
      </div>
    </div>
  );
}
