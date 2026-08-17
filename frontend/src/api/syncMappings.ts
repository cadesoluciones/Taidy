import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export interface SystemRef {
  system: string;
  table: string;
}

export interface FieldPair {
  source: string;
  target: string;
}

export interface SyncMappingConfig {
  name: string;
  description: string;
  source: SystemRef;
  target: SystemRef;
  matching_key: FieldPair;
  date_field: FieldPair;
  fields: FieldPair[];
}

export interface SyncMappingInput {
  source: SystemRef;
  target: SystemRef;
  matching_key: FieldPair;
  date_field: FieldPair;
  fields: FieldPair[];
  description?: string;
}

export interface RecordAction {
  key: string;
  kind: string;
  source_row: Record<string, unknown> | null;
  target_row: Record<string, unknown> | null;
  source_date: string | null;
  target_date: string | null;
}

export interface SkippedRecord {
  system: string;
  reason: string;
  key: string;
  row: Record<string, unknown>;
}

export interface ComparisonReport {
  mapping_name: string;
  create_in_target: RecordAction[];
  create_in_source: RecordAction[];
  update_target: RecordAction[];
  update_source: RecordAction[];
  unchanged: RecordAction[];
  skipped: SkippedRecord[];
}

export function fetchSyncMappings(): Promise<{ items: SyncMappingConfig[] }> {
  return apiGet<{ items: SyncMappingConfig[] }>("/sync/mappings");
}

export function createSyncMapping(input: SyncMappingInput & { name: string }): Promise<SyncMappingConfig> {
  return apiPost<SyncMappingConfig>("/sync/mappings", input);
}

export function updateSyncMapping(name: string, input: SyncMappingInput): Promise<SyncMappingConfig> {
  return apiPatch<SyncMappingConfig>(`/sync/mappings/${encodeURIComponent(name)}`, input);
}

export function deleteSyncMapping(name: string): Promise<void> {
  return apiDelete<void>(`/sync/mappings/${encodeURIComponent(name)}`);
}

export function compareSyncMapping(name: string): Promise<ComparisonReport> {
  return apiPost<ComparisonReport>(`/sync/mappings/${encodeURIComponent(name)}/compare`);
}
