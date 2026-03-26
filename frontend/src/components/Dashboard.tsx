/**
 * Clinical Dashboard — Overview of active sessions, pipeline health, and stats.
 */

import { useQuery } from "@tanstack/react-query";

interface DashboardStats {
  active_sessions: number;
  total_encounters_today: number;
  avg_soap_generation_time_ms: number;
  emergency_escalations_today: number;
  specialties_seen: Record<string, number>;
  system_health: {
    api: boolean;
    asr: boolean;
    llm: boolean;
    ner: boolean;
    database: boolean;
  };
}

async function fetchStats(): Promise<DashboardStats> {
  const resp = await fetch("/api/dashboard/stats");
  if (!resp.ok) throw new Error("Failed to fetch dashboard stats");
  return resp.json();
}

export function Dashboard() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: fetchStats,
    refetchInterval: 15_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-800">Failed to load dashboard: {String(error)}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Clinical Dashboard</h1>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Active Sessions"
          value={stats?.active_sessions ?? 0}
          color="blue"
        />
        <StatCard
          label="Encounters Today"
          value={stats?.total_encounters_today ?? 0}
          color="green"
        />
        <StatCard
          label="Avg SOAP Time"
          value={`${stats?.avg_soap_generation_time_ms ?? 0}ms`}
          color="purple"
        />
        <StatCard
          label="Emergencies"
          value={stats?.emergency_escalations_today ?? 0}
          color={stats?.emergency_escalations_today ? "red" : "gray"}
        />
      </div>

      {/* System Health */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">System Health</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {stats?.system_health &&
            Object.entries(stats.system_health).map(([service, healthy]) => (
              <div
                key={service}
                className={`flex items-center gap-2 p-3 rounded-lg ${
                  healthy ? "bg-green-50" : "bg-red-50"
                }`}
              >
                <span
                  className={`h-3 w-3 rounded-full ${
                    healthy ? "bg-green-500" : "bg-red-500"
                  }`}
                />
                <span className="text-sm font-medium capitalize">{service}</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    green: "bg-green-50 text-green-700 border-green-200",
    purple: "bg-purple-50 text-purple-700 border-purple-200",
    red: "bg-red-50 text-red-700 border-red-200",
    gray: "bg-gray-50 text-gray-700 border-gray-200",
  };

  return (
    <div className={`rounded-lg border p-4 ${colorMap[color] ?? colorMap.gray}`}>
      <p className="text-sm font-medium opacity-80">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
    </div>
  );
}
