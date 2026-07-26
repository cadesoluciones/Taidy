import { apiGet, apiUrl, buildQuery } from "./client";

export interface AuditEntry {
  ts: string;
  event: string;
  outcome: string;
  user: string;
  detail: string;
}

export interface AuditPage {
  items: AuditEntry[];
  total_matching: number;
  total_available: number;
}

export interface AuditFilters {
  event?: string[];
  user?: string[];
  outcome?: string[];
  date_from?: string;
  date_to?: string;
}

export function fetchAudit(filters: AuditFilters = {}): Promise<AuditPage> {
  return apiGet<AuditPage>(`/audit${buildQuery(filters)}`);
}

export function auditExportCsvUrl(filters: AuditFilters): string {
  return apiUrl(`/audit/export.csv${buildQuery(filters)}`);
}
