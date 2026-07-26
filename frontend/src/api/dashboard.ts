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

export interface ErrorRateAlert {
  action: string;
  recent_failures: number;
  recent_total: number;
}

export interface DashboardSummary {
  running_count: number;
  active_schedule_count: number;
  recent_error_count: number;
  recent_history: RecentRun[];
  error_rate_alerts: ErrorRateAlert[];
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

export interface NarrativeSummary {
  text: string;
  mode_used: "template" | "llm";
  llm_provider: string | null;
}

/** On-demand only -- never polled, unlike fetchDashboardSummary above (an
 * LLM-generated summary has real latency and, depending on the configured
 * provider, real cost). mode "llm" falls back to "template" server-side
 * (reflected in mode_used) when no provider is configured or the call fails. */
export function fetchNarrativeSummary(mode: "template" | "llm"): Promise<NarrativeSummary> {
  return apiGet<NarrativeSummary>(`/dashboard/narrative-summary?mode=${mode}`);
}
