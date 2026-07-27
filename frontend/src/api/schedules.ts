import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export interface Schedule {
  id: string;
  name: string;
  action: string;
  params: Record<string, unknown>;
  trigger: "interval" | "cron";
  trigger_args: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  next_run_time: string | null;
  missed_last_run: boolean;
}

export interface CreateScheduleInput {
  name: string;
  action: string;
  params?: Record<string, unknown>;
  trigger: "interval" | "cron";
  trigger_args: Record<string, unknown>;
}

export function fetchSchedules(): Promise<{ items: Schedule[] }> {
  return apiGet<{ items: Schedule[] }>("/schedules");
}

export function createSchedule(input: CreateScheduleInput): Promise<Schedule> {
  return apiPost<Schedule>("/schedules", input);
}

export function setScheduleEnabled(id: string, enabled: boolean): Promise<void> {
  return apiPatch<void>(`/schedules/${id}`, { enabled });
}

export function deleteSchedule(id: string): Promise<void> {
  return apiDelete<void>(`/schedules/${id}`);
}

/** schedule_id -> ISO datetimes it's due to fire between this week's Monday
 * and Sunday -- backs Inicio's weekly calendar. */
export function fetchSchedulesWeek(): Promise<{ occurrences: Record<string, string[]> }> {
  return apiGet<{ occurrences: Record<string, string[]> }>("/schedules/week");
}
