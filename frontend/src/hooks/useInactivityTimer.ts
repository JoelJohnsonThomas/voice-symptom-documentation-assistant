import { useCallback, useEffect, useRef, useState } from "react";

interface UseInactivityTimerOptions {
  timeoutMs: number;
  warningMs?: number;
  onTimeout: () => void;
  onWarning?: () => void;
  enabled?: boolean;
}

export function useInactivityTimer({
  timeoutMs,
  warningMs,
  onTimeout,
  onWarning,
  enabled = true,
}: UseInactivityTimerOptions) {
  const [showWarning, setShowWarning] = useState(false);
  const timeoutRef = useRef<number>(0);
  const warningRef = useRef<number>(0);

  const resetTimer = useCallback(() => {
    setShowWarning(false);
    clearTimeout(timeoutRef.current);
    clearTimeout(warningRef.current);

    if (!enabled) return;

    if (warningMs) {
      warningRef.current = window.setTimeout(() => {
        setShowWarning(true);
        onWarning?.();
      }, timeoutMs - warningMs);
    }

    timeoutRef.current = window.setTimeout(() => {
      onTimeout();
    }, timeoutMs);
  }, [timeoutMs, warningMs, onTimeout, onWarning, enabled]);

  useEffect(() => {
    if (!enabled) return;

    const events = ["mousedown", "keydown", "touchstart", "scroll"] as const;
    events.forEach((e) => document.addEventListener(e, resetTimer, { passive: true }));
    resetTimer();

    return () => {
      events.forEach((e) => document.removeEventListener(e, resetTimer));
      clearTimeout(timeoutRef.current);
      clearTimeout(warningRef.current);
    };
  }, [resetTimer, enabled]);

  return { showWarning, resetTimer };
}
