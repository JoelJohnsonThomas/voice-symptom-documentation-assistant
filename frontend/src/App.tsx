import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppLayout } from "./components/layout/AppLayout";
import { Spinner } from "./components/ui/Spinner";
import { PwaUpdatePrompt } from "./components/ui/PwaUpdatePrompt";

// Lazy-loaded pages
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const SessionPage = lazy(() => import("./pages/SessionPage"));
const SessionHistoryPage = lazy(() => import("./pages/SessionHistoryPage"));
const SessionViewPage = lazy(() => import("./pages/SessionViewPage"));
const AmbientModePage = lazy(() => import("./pages/AmbientModePage"));
const MonitoringPage = lazy(() => import("./pages/MonitoringPage"));
const HIPAAPage = lazy(() => import("./pages/HIPAAPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const OfflineFallbackPage = lazy(() => import("./pages/OfflineFallbackPage"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

function PageLoader() {
  return (
    <div className="flex h-full items-center justify-center">
      <Spinner size="lg" />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<DashboardPage />} />
              <Route path="session" element={<SessionPage />} />
              <Route path="session/:id" element={<SessionViewPage />} />
              <Route path="history" element={<SessionHistoryPage />} />
              <Route path="ambient" element={<AmbientModePage />} />
              <Route path="monitoring" element={<MonitoringPage />} />
              <Route path="hipaa" element={<HIPAAPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="offline" element={<OfflineFallbackPage />} />
            </Route>
          </Routes>
        </Suspense>
        <PwaUpdatePrompt />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
