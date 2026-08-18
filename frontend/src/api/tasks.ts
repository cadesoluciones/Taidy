import { apiGet, apiPost, buildQuery } from "./client";
import type { TableStatus, TaskStatus } from "./types";

export interface Task {
  id: string;
  action: string;
  action_label: string;
  triggered_by: string;
  status: TaskStatus;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number;
  current_step: number;
  step_labels: string[];
  table_statuses: TableStatus[];
  log_tail: string;
}

export interface TaskFilters {
  action?: string[];
  user?: string[];
  status?: string[];
  date_from?: string;
  date_to?: string;
}

export function fetchTasks(filters: TaskFilters = {}): Promise<{ items: Task[] }> {
  return apiGet<{ items: Task[] }>(`/tasks${buildQuery(filters)}`);
}

export function fetchTask(id: string): Promise<Task> {
  return apiGet<Task>(`/tasks/${id}`);
}

export function stopTask(id: string): Promise<void> {
  return apiPost<void>(`/tasks/${id}/stop`);
}

export interface ExtractBcInput {
  tables?: string[] | null;
  output_dir?: string;
  page_size?: number | null;
  mode?: "incremental" | "full";
  parallel?: number;
  dry_run?: boolean;
  reset_watermarks?: boolean;
  checkpoint_path?: string;
  verbose?: boolean;
  notify?: boolean;
}
export function extractBc(input: ExtractBcInput): Promise<Task> {
  return apiPost<Task>("/tasks/extract-bc", input);
}

export interface UploadBcInput {
  output_dir?: string;
  dry_run?: boolean;
  skip_existing?: boolean;
  verbose?: boolean;
  notify?: boolean;
}
export function uploadBc(input: UploadBcInput): Promise<Task> {
  return apiPost<Task>("/tasks/upload-bc", input);
}

export interface SyncBcInput {
  tables?: string[] | null;
  output_dir?: string;
  mode?: "incremental" | "full";
  parallel?: number;
  dry_run?: boolean;
  skip_existing?: boolean;
  verbose?: boolean;
  notify?: boolean;
}
export function syncBc(input: SyncBcInput): Promise<Task> {
  return apiPost<Task>("/tasks/sync-bc", input);
}

export interface ExtractFactorialInput {
  start_on: string;
  end_on: string;
  employees?: number[] | null;
  employee_status?: "active" | "inactive" | "all";
  tables?: string[] | null;
  output_dir?: string;
  mode?: "full" | "incremental";
  parallel?: number;
  reset_all_checkpoints?: boolean;
  dry_run?: boolean;
  verbose?: boolean;
  notify?: boolean;
}
export function extractFactorial(input: ExtractFactorialInput): Promise<Task> {
  return apiPost<Task>("/tasks/extract-factorial", input);
}

export interface UploadFactorialInput {
  output_dir?: string;
  tables?: string[] | null;
  dry_run?: boolean;
  skip_existing?: boolean;
  verbose?: boolean;
  notify?: boolean;
}
export function uploadFactorial(input: UploadFactorialInput): Promise<Task> {
  return apiPost<Task>("/tasks/upload-factorial", input);
}

export interface SyncFactorialInput {
  start_on: string;
  end_on: string;
  employee_status?: "active" | "inactive" | "all";
  tables?: string[] | null;
  output_dir?: string;
  mode?: "incremental" | "full";
  parallel?: number;
  dry_run?: boolean;
  skip_existing?: boolean;
  verbose?: boolean;
  notify?: boolean;
}
export function syncFactorial(input: SyncFactorialInput): Promise<Task> {
  return apiPost<Task>("/tasks/sync-factorial", input);
}

export interface ExtractHubspotInput {
  tables?: string[] | null;
  output_dir?: string;
  parallel?: number;
  dry_run?: boolean;
  verbose?: boolean;
  notify?: boolean;
}
export function extractHubspot(input: ExtractHubspotInput): Promise<Task> {
  return apiPost<Task>("/tasks/extract-hubspot", input);
}

export interface UploadHubspotInput {
  output_dir?: string;
  tables?: string[] | null;
  dry_run?: boolean;
  skip_existing?: boolean;
  verbose?: boolean;
  notify?: boolean;
}
export function uploadHubspot(input: UploadHubspotInput): Promise<Task> {
  return apiPost<Task>("/tasks/upload-hubspot", input);
}

export interface SyncHubspotInput {
  tables?: string[] | null;
  output_dir?: string;
  parallel?: number;
  dry_run?: boolean;
  skip_existing?: boolean;
  verbose?: boolean;
  notify?: boolean;
}
export function syncHubspot(input: SyncHubspotInput): Promise<Task> {
  return apiPost<Task>("/tasks/sync-hubspot", input);
}

export interface RunPipelineInput {
  pipeline: string;
  wait?: boolean;
  poll_seconds?: number;
  verbose?: boolean;
  notify?: boolean;
}
export function runPipeline(input: RunPipelineInput): Promise<Task> {
  return apiPost<Task>("/tasks/run-pipeline", input);
}

export type SyncApplyDirection = "to_target" | "to_source" | "both";

export interface SyncApplyInput {
  mapping: string;
  direction: SyncApplyDirection;
  // Matching-key values (e.g. emails) to restrict this run to -- omit/undefined
  // means every pending action.
  keys?: string[];
  confirm_large_batch?: boolean;
  verbose?: boolean;
  notify?: boolean;
}
export function syncApply(input: SyncApplyInput): Promise<Task> {
  return apiPost<Task>("/tasks/sync-apply", input);
}
