import { useState, useCallback, createContext, useContext, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error" | "warning" | "info";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

const typeStyles: Record<ToastType, string> = {
  success: "border-[rgba(16,185,129,0.3)] bg-[rgba(16,185,129,0.1)]",
  error: "border-[rgba(244,63,94,0.3)] bg-[rgba(244,63,94,0.1)]",
  warning: "border-[rgba(245,158,11,0.3)] bg-[rgba(245,158,11,0.1)]",
  info: "border-[rgba(99,102,241,0.3)] bg-[rgba(99,102,241,0.1)]",
};

const typeIcons: Record<ToastType, string> = {
  success: "text-[var(--emerald-500)]",
  error: "text-[var(--rose-500)]",
  warning: "text-[var(--amber-500)]",
  info: "text-[var(--indigo-500)]",
};

let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: ToastType = "info") => {
    const id = nextId++;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}
      {/* Toast container */}
      <div className="fixed bottom-6 right-6 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            onClick={() => removeToast(t.id)}
            className={cn(
              "pointer-events-auto px-4 py-3 rounded-[var(--radius-md)]",
              "border backdrop-blur-lg shadow-lg",
              "text-sm font-medium text-[var(--text-primary)]",
              "cursor-pointer animate-[slide-in-right_0.3s_ease-out]",
              "flex items-center gap-2",
              typeStyles[t.type]
            )}
          >
            <span className={cn("text-base", typeIcons[t.type])}>
              {t.type === "success" && "✓"}
              {t.type === "error" && "✕"}
              {t.type === "warning" && "⚠"}
              {t.type === "info" && "ℹ"}
            </span>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
