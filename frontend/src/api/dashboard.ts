import { apiGet } from "./client";

export interface RecentRun {
  action: string;
  source: string;
  ok: boolean;
  status: string;
  finished_at: string;
  message: string;
}

export interface DashboardSummary {
  running_count: number;
  active_schedule_count: number;
  recent_error_count: number;
  recent_history: RecentRun[];
}

export function fetchDashboardSummary(): Promise<DashboardSummary> {
  return apiGet<DashboardSummary>("/dashboard/summary");
}
