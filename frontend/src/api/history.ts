import { apiGet, buildQuery } from "./client";

export interface HistoryEntry {
  action: string;
  source: string;
  status: string;
  ok: boolean;
  message: string;
  duration_seconds: number | null;
  finished_at: string;
  log: string;
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
