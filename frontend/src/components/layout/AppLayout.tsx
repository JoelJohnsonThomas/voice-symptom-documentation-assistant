import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useTheme } from "../../hooks/useTheme";
import { ToastProvider } from "../ui/Toaster";

export function AppLayout() {
  // Initialize theme on mount
  useTheme();

  return (
    <ToastProvider>
      <div className="flex h-screen overflow-hidden bg-[var(--bg-primary)] text-[var(--text-primary)]">
        <Sidebar />
        <main className="flex flex-1 flex-col overflow-hidden">
          <Outlet />
        </main>
      </div>
    </ToastProvider>
  );
}
