import { Clock } from "lucide-react";
import { Modal } from "../ui/Modal";

interface SessionTimeoutWarningProps {
  isOpen: boolean;
  onExtend: () => void;
  onLogout: () => void;
}

export function SessionTimeoutWarning({
  isOpen,
  onExtend,
  onLogout,
}: SessionTimeoutWarningProps) {
  return (
    <Modal open={isOpen} onClose={onExtend} title="Session Expiring">
      <div className="space-y-4">
        <div className="flex items-start gap-3">
          <Clock
            size={20}
            className="mt-0.5 shrink-0 text-[var(--status-warning)]"
          />
          <p className="text-sm text-[var(--text-secondary)]">
            Your session will expire due to inactivity. Click below to continue
            or you will be automatically signed out.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onExtend}
            className="flex-1 rounded-lg bg-[var(--accent-primary)] py-2 text-sm font-medium text-white hover:bg-[var(--accent-primary)]/80"
          >
            Stay Signed In
          </button>
          <button
            onClick={onLogout}
            className="flex-1 rounded-lg border border-[var(--border-primary)] py-2 text-sm text-[var(--text-muted)] hover:bg-white/[0.06]"
          >
            Sign Out
          </button>
        </div>
      </div>
    </Modal>
  );
}
