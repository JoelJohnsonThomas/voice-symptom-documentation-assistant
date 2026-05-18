import { useEffect, useState } from "react";
import { Download, RefreshCw, WifiOff, X } from "lucide-react";

interface PwaUpdatePromptProps {
  onUpdate?: () => void;
}

declare global {
  interface WindowEventMap {
    "voxdoc:pwa-need-refresh": CustomEvent<{ update: () => Promise<void> }>;
    "voxdoc:pwa-offline-ready": CustomEvent;
  }
}

export function PwaUpdatePrompt({ onUpdate }: PwaUpdatePromptProps) {
  const [needRefresh, setNeedRefresh] = useState(false);
  const [offlineReady, setOfflineReady] = useState(false);
  const [updateFn, setUpdateFn] = useState<(() => Promise<void>) | null>(null);

  useEffect(() => {
    const onNeedRefresh = (e: CustomEvent<{ update: () => Promise<void> }>) => {
      setUpdateFn(() => e.detail.update);
      setNeedRefresh(true);
    };
    const onOfflineReady = () => {
      setOfflineReady(true);
      setTimeout(() => setOfflineReady(false), 4000);
    };
    window.addEventListener("voxdoc:pwa-need-refresh", onNeedRefresh);
    window.addEventListener("voxdoc:pwa-offline-ready", onOfflineReady);
    return () => {
      window.removeEventListener("voxdoc:pwa-need-refresh", onNeedRefresh);
      window.removeEventListener("voxdoc:pwa-offline-ready", onOfflineReady);
    };
  }, []);

  const handleUpdate = async () => {
    if (updateFn) await updateFn();
    setNeedRefresh(false);
    onUpdate?.();
  };

  if (!needRefresh && !offlineReady) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 max-w-xs rounded-lg border border-[var(--border-primary)] bg-[var(--bg-card)] p-3 shadow-2xl"
    >
      {needRefresh ? (
        <div className="flex items-start gap-2">
          <Download size={16} className="mt-0.5 shrink-0 text-[var(--accent-primary)]" />
          <div className="flex-1 text-xs">
            <p className="font-medium text-[var(--text-primary)]">Update available</p>
            <p className="mt-0.5 text-[var(--text-muted)]">
              A new version of VoxDoc is ready.
            </p>
            <div className="mt-2 flex gap-1">
              <button
                type="button"
                onClick={handleUpdate}
                className="inline-flex items-center gap-1 rounded bg-[var(--accent-primary)] px-2 py-1 text-[10px] font-medium text-white"
              >
                <RefreshCw size={10} />
                Reload
              </button>
              <button
                type="button"
                onClick={() => setNeedRefresh(false)}
                aria-label="Dismiss"
                className="rounded p-1 text-[var(--text-muted)] hover:bg-white/[0.06]"
              >
                <X size={12} />
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs">
          <WifiOff size={14} className="text-[var(--status-online)]" />
          <span className="text-[var(--text-secondary)]">App ready to work offline</span>
        </div>
      )}
    </div>
  );
}
