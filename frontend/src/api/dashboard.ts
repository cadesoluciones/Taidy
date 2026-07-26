import { apiGet } from "./client";
import type { WorkflowRun } from "./workflows";

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

export interface MyWorkflowStatus {
  id: string;
  name: string;
  current_run: WorkflowRun | null;
  last_run: WorkflowRun | null;
  scheduled: boolean;
}

export function fetchMyWorkflows(): Promise<{ items: MyWorkflowStatus[] }> {
  return apiGet<{ items: MyWorkflowStatus[] }>("/dashboard/mine-workflows");
}
