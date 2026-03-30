import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useTheme } from "../../hooks/useTheme";
import { ToastProvider } from "../ui/Toaster";

export function AppLayout() {
  useTheme();

  return (
    <ToastProvider>
      <div className="app-shell">
        <Sidebar />
        <main className="main-area">
          <Outlet />
        </main>
      </div>
    </ToastProvider>
  );
}
