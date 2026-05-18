import { type ReactNode, useCallback, useEffect } from "react";
import { cn } from "@/lib/utils";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  side?: "right" | "left";
  width?: string;
  children: ReactNode;
}

export function Drawer({
  open,
  onClose,
  title,
  side = "right",
  width = "min(28rem, 92vw)",
  children,
}: DrawerProps) {
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    document.addEventListener("keydown", handleKey);
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = original;
    };
  }, [open, handleKey]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex" aria-hidden={!open}>
      <button
        type="button"
        aria-label="Close drawer"
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-[fade-in_0.15s_ease-out]"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{ width }}
        className={cn(
          "relative z-10 ml-auto flex h-full flex-col border-l border-[var(--border-color)] bg-[var(--bg-card)] shadow-2xl",
          side === "left" && "ml-0 mr-auto border-l-0 border-r",
        )}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-[var(--border-color)] px-5 py-4">
            <h3 className="text-base font-semibold text-[var(--text-primary)]">{title}</h3>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-md p-1 text-[var(--text-muted)] hover:bg-white/[0.06] hover:text-[var(--text-primary)]"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </aside>
    </div>
  );
}
