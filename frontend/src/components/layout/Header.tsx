import { Bell, Wifi, WifiOff } from "lucide-react";
import { useWebSocketStore } from "../../stores/websocketStore";

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
    <header className="main-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="header-right">
        {actions}
        <div className={`ws-status${anyConnected ? " connected" : ""}`}>
          {anyConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
          {anyConnected ? "Live" : "Offline"}
        </div>
        <span className="version-badge">v2.0</span>
        <button className="header-icon-btn" aria-label="Notifications">
          <Bell size={16} />
        </button>
      </div>
    </header>
  );
}
