import { apiGet, apiUrl, buildQuery } from "./client";

export interface SyncApplyRecordDetail {
  key: string;
  kind: string;
  outcome: "created" | "updated" | "skipped" | "failed";
  detail: string;
}

export interface HistoryEntry {
  action: string;
  source: string;
  status: string;
  ok: boolean;
  message: string;
  duration_seconds: number | null;
  finished_at: string;
  log: string;
  // Only present for actions with a per-record breakdown (currently
  // sync_apply) -- absent/null for every other action's entries.
  details: SyncApplyRecordDetail[] | null;
}

export interface HistoryPage {
  items: HistoryEntry[];
  total_matching: number;
  total_available: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface HistoryFilters {
  action?: string[];
  source?: string[];
  result?: "all" | "ok" | "error" | "stopped";
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export function fetchHistory(filters: HistoryFilters = {}): Promise<HistoryPage> {
  return apiGet<HistoryPage>(`/history${buildQuery(filters)}`);
}

/** Filters minus pagination -- the export always covers the full filtered
 * set, not one page of it. */
export function historyExportCsvUrl(filters: Omit<HistoryFilters, "page" | "page_size">): string {
  return apiUrl(`/history/export.csv${buildQuery(filters)}`);
}
