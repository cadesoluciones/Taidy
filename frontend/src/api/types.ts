/** Shared status vocabulary -- must match the backend exactly (webapp/tasks.py,
 * workflow_engine.py, adapter.py); never invent a new client-side state. */
export type TaskStatus = "running" | "stopping" | "ok" | "error" | "stopped";
export type StepStatus = "pending" | "running" | "ok" | "error" | "cancelled" | "stopped";
export type TableStatusValue = "ok" | "skipped" | "dry_run" | "error" | "unknown" | "in_progress";

export interface TableStatus {
  name: string;
  status: TableStatusValue;
  detail: string;
  phase: string;
}
