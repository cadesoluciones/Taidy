import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type { StepStatus } from "./types";

export interface StepDefinition {
  id: string;
  label: string;
  action: string;
  params: Record<string, unknown>;
  depends_on: string[];
  trigger_rule: "all_success" | "always";
}

export interface Workflow {
  id: string;
  name: string;
  steps: StepDefinition[];
  created_at: string;
  reader_allowed_users: string[];
}

export interface StepRun {
  id: string;
  label: string;
  action: string;
  depends_on: string[];
  trigger_rule: string;
  status: StepStatus;
  task_id: string | null;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  workflow_name: string;
  triggered_by: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "ok" | "error" | "stopped";
  duration_seconds: number;
  steps: StepRun[];
}

export function fetchWorkflows(): Promise<{ items: Workflow[] }> {
  return apiGet<{ items: Workflow[] }>("/workflows");
}

export function createWorkflow(name: string, steps: StepDefinition[]): Promise<Workflow> {
  return apiPost<Workflow>("/workflows", { name, steps });
}

export function updateWorkflow(id: string, name: string, steps: StepDefinition[]): Promise<Workflow> {
  return apiPatch<Workflow>(`/workflows/${id}`, { name, steps });
}

export function deleteWorkflow(id: string): Promise<void> {
  return apiDelete<void>(`/workflows/${id}`);
}

export function setWorkflowReaderAccess(id: string, readerUsernames: string[]): Promise<Workflow> {
  return apiPatch<Workflow>(`/workflows/${id}/reader-access`, { reader_usernames: readerUsernames });
}

export function runWorkflow(id: string, notify = false): Promise<WorkflowRun> {
  return apiPost<WorkflowRun>(`/workflows/${id}/run`, { notify });
}

export function fetchWorkflowRuns(): Promise<{ items: WorkflowRun[] }> {
  return apiGet<{ items: WorkflowRun[] }>("/workflow-runs");
}

export function stopWorkflowRun(runId: string): Promise<void> {
  return apiPost<void>(`/workflow-runs/${runId}/stop`);
}

/** Re-runs only the step(s) that failed (plus anything cascade-cancelled
 * because of them) -- only valid while the run's status is "error". */
export function retryWorkflowRun(runId: string): Promise<WorkflowRun> {
  return apiPost<WorkflowRun>(`/workflow-runs/${runId}/retry`);
}
