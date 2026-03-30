import type { SystemHealth } from "../../types/api";

interface SystemHealthGridProps {
  health: SystemHealth | null;
}

export function SystemHealthGrid({ health }: SystemHealthGridProps) {
  if (!health) return null;

  const items: { label: string; status: "up" | "warn" | "down" }[] = [
    { label: "API Server", status: health.status === "healthy" ? "up" : "down" },
    { label: "Whisper ASR", status: "up" },
    { label: `CPU ${health.cpu}%`, status: health.cpu > 80 ? "warn" : "up" },
    { label: `Mem ${health.memory}%`, status: health.memory > 85 ? "warn" : "up" },
    { label: "Database", status: "up" },
    { label: "WebSocket", status: "up" },
    { label: `Uptime ${Math.floor(health.uptime / 3600)}h`, status: "up" },
    { label: "HIPAA Enc", status: "up" },
  ];

  return (
    <>
      {items.map((item) => (
        <div key={item.label} className="health-item">
          <div className={`health-dot ${item.status}`} />
          <span className="health-label">{item.label}</span>
        </div>
      ))}
    </>
  );
}
