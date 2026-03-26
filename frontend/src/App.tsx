/**
 * Voice Triage Clinical Dashboard (Phase 4)
 *
 * React 19 + Vite + TailwindCSS frontend for the Voice Symptom
 * Triage Assistant. Mobile-first clinical documentation dashboard.
 *
 * Routes:
 *   /            → Dashboard (active sessions, stats)
 *   /session/:id → Live session view with streaming SOAP
 *   /history     → Past encounters with search
 *   /ambient     → Ambient documentation mode
 *   /settings    → User & system configuration
 */

import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./components/Layout";
import { Dashboard } from "./components/Dashboard";
import { SessionView } from "./components/SessionView";
import { SessionHistory } from "./components/SessionHistory";
import { AmbientMode } from "./components/AmbientMode";
import { Settings } from "./components/Settings";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="session/:id" element={<SessionView />} />
            <Route path="history" element={<SessionHistory />} />
            <Route path="ambient" element={<AmbientMode />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
