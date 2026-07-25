import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export function fetchBcTables(): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>("/meta/bc-tables");
}

export function fetchFactorialTables(): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>("/meta/factorial-tables");
}

export function fetchPipelines(): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>("/meta/pipelines");
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
