import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export function fetchBcTables(): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>("/meta/bc-tables");
}

export function fetchFactorialTables(): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>("/meta/factorial-tables");
}

export function fetchHubspotTables(): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>("/meta/hubspot-tables");
}

export function fetchPipelines(): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>("/meta/pipelines");
}

export interface HubspotTableConfig {
  name: string;
  description: string;
  object_type: string;
  fields: string[];
}

export interface CreateHubspotTableInput {
  name: string;
  object_type: string;
  fields: string[];
  description?: string;
}

export function fetchHubspotTablesFull(): Promise<{ items: HubspotTableConfig[] }> {
  return apiGet<{ items: HubspotTableConfig[] }>("/meta/hubspot-tables/full");
}

export function createHubspotTable(input: CreateHubspotTableInput): Promise<HubspotTableConfig> {
  return apiPost<HubspotTableConfig>("/meta/hubspot-tables", input);
}

export type UpdateHubspotTableInput = Omit<CreateHubspotTableInput, "name">;

export function updateHubspotTable(name: string, input: UpdateHubspotTableInput): Promise<HubspotTableConfig> {
  return apiPatch<HubspotTableConfig>(`/meta/hubspot-tables/${encodeURIComponent(name)}`, input);
}

export function deleteHubspotTable(name: string): Promise<void> {
  return apiDelete<void>(`/meta/hubspot-tables/${encodeURIComponent(name)}`);
}

export interface BcTableConfig {
  name: string;
  description: string;
  url: string;
  incremental: boolean;
}

export interface CreateBcTableInput {
  name: string;
  url: string;
  description?: string;
  incremental?: boolean;
}

export function fetchBcTablesFull(): Promise<{ items: BcTableConfig[] }> {
  return apiGet<{ items: BcTableConfig[] }>("/meta/bc-tables/full");
}

export function createBcTable(input: CreateBcTableInput): Promise<BcTableConfig> {
  return apiPost<BcTableConfig>("/meta/bc-tables", input);
}

export type UpdateBcTableInput = Omit<CreateBcTableInput, "name">;

export function updateBcTable(name: string, input: UpdateBcTableInput): Promise<BcTableConfig> {
  return apiPatch<BcTableConfig>(`/meta/bc-tables/${encodeURIComponent(name)}`, input);
}

export function deleteBcTable(name: string): Promise<void> {
  return apiDelete<void>(`/meta/bc-tables/${encodeURIComponent(name)}`);
}

/** BC never declares a field list in tables.yaml (unlike Factorial/HubSpot) --
 * this reads the header row of the table's last real extraction instead, so
 * the sync-mapping UI has *something* to drag from. Empty if never extracted. */
export function fetchBcTableFields(name: string): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>(`/meta/bc-tables/${encodeURIComponent(name)}/fields`);
}

export interface FactorialTableConfig {
  name: string;
  description: string;
  path: string;
  fields: string[];
  date_range: boolean;
  employee_filter: boolean;
  incremental: boolean;
  overlap_days: number | null;
  chunk_days: number | null;
}

export interface CreateFactorialTableInput {
  name: string;
  path: string;
  fields: string[];
  description?: string;
  date_range?: boolean;
  employee_filter?: boolean;
  incremental?: boolean;
  overlap_days?: number | null;
  chunk_days?: number | null;
}

export function fetchFactorialTablesFull(): Promise<{ items: FactorialTableConfig[] }> {
  return apiGet<{ items: FactorialTableConfig[] }>("/meta/factorial-tables/full");
}

export function createFactorialTable(input: CreateFactorialTableInput): Promise<FactorialTableConfig> {
  return apiPost<FactorialTableConfig>("/meta/factorial-tables", input);
}

export type UpdateFactorialTableInput = Omit<CreateFactorialTableInput, "name">;

export function updateFactorialTable(name: string, input: UpdateFactorialTableInput): Promise<FactorialTableConfig> {
  return apiPatch<FactorialTableConfig>(`/meta/factorial-tables/${encodeURIComponent(name)}`, input);
}

export function deleteFactorialTable(name: string): Promise<void> {
  return apiDelete<void>(`/meta/factorial-tables/${encodeURIComponent(name)}`);
}
