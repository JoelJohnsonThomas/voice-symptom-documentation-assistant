import { LogOut, ChevronUp } from "lucide-react";
import { useState } from "react";
import { cn } from "../../lib/utils";
import { useAuth } from "../../hooks/useAuth";

interface UserCardProps {
  collapsed?: boolean;
}

export function UserCard({ collapsed }: UserCardProps) {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!user) return null;

  const initials = user.name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="relative border-t border-[var(--border-primary)] p-3">
      <button
        onClick={() => setMenuOpen(!menuOpen)}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors hover:bg-white/[0.06]",
          collapsed && "justify-center"
        )}
      >
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] text-xs font-bold text-white">
          {initials}
        </div>
        {!collapsed && (
          <>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                {user.name}
              </p>
              <p className="truncate text-xs text-[var(--text-muted)]">
                {user.role}
              </p>
            </div>
            <ChevronUp
              size={16}
              className={cn(
                "text-[var(--text-muted)] transition-transform",
                menuOpen && "rotate-180"
              )}
            />
          </>
        )}
      </button>

      {menuOpen && (
        <div className="absolute bottom-full left-3 right-3 mb-1 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] p-1 shadow-xl">
          <button
            onClick={() => {
              logout();
              setMenuOpen(false);
            }}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-[var(--status-error)] hover:bg-white/[0.06]"
          >
            <LogOut size={16} />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
