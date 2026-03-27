import { Bell, Download, Wifi, WifiOff } from "lucide-react";
import { useWebSocketStore } from "../../stores/websocketStore";
import { StatusDot } from "../ui/StatusDot";
import { IconButton } from "../ui/IconButton";
import { cn } from "../../lib/utils";

interface HeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export function Header({ title, subtitle, actions }: HeaderProps) {
  const wsState = useWebSocketStore();
  const anyConnected =
    wsState.transcription === "connected" ||
    wsState.conversation === "connected" ||
    wsState.soap === "connected";

  return (
    <header className="flex items-center justify-between border-b border-[var(--border-primary)] bg-[var(--bg-secondary)]/60 px-6 py-3 backdrop-blur-sm">
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          {title}
        </h2>
        {subtitle && (
          <p className="text-sm text-[var(--text-muted)]">{subtitle}</p>
        )}
      </div>

      <div className="flex items-center gap-3">
        {actions}

        {/* WebSocket status */}
        <div
          className={cn(
            "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs",
            anyConnected
              ? "border-[var(--status-online)]/30 text-[var(--status-online)]"
              : "border-[var(--border-primary)] text-[var(--text-muted)]"
          )}
        >
          {anyConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
          {anyConnected ? "Live" : "Offline"}
        </div>

        <IconButton aria-label="Notifications">
          <Bell size={18} />
        </IconButton>
      </div>
    </header>
  );
}
