import { WifiOff } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";

export default function OfflineFallbackPage() {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <GlassCard className="max-w-md p-6 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--status-warning)]/10 text-[var(--status-warning)]">
          <WifiOff size={22} />
        </div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">You're offline</h2>
        <p className="mt-2 text-sm text-[var(--text-muted)]">
          VoxDoc can't reach the clinical documentation server. Cached pages still load, but live
          transcription, SOAP generation, and FHIR push require a connection. Reconnect to resume
          work.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-4 rounded-md bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white"
        >
          Retry
        </button>
      </GlassCard>
    </div>
  );
}
