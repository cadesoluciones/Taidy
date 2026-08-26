import { apiDelete, apiGet, apiPatch, apiPost, buildQuery } from "./client";

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

export type UpdateHubspotTableInput = CreateHubspotTableInput;

export function updateHubspotTable(name: string, input: UpdateHubspotTableInput): Promise<HubspotTableConfig> {
  return apiPatch<HubspotTableConfig>(`/meta/hubspot-tables/${encodeURIComponent(name)}`, input);
}

export function deleteHubspotTable(name: string): Promise<void> {
  return apiDelete<void>(`/meta/hubspot-tables/${encodeURIComponent(name)}`);
}

export interface AvailableProperty {
  name: string;
  label: string;
}

/** Live "what can I extract?" discovery, used by the admin UI's available-
 * properties picker -- takes the object type currently typed in the form,
 * not a saved table name, so it works before the table entry even exists.
 * Hidden/calculated HubSpot properties are excluded unless includeHidden. */
export function fetchHubspotAvailableProperties(
  objectType: string,
  includeHidden = false
): Promise<{ items: AvailableProperty[] }> {
  return apiGet<{ items: AvailableProperty[] }>(
    `/meta/hubspot-tables/available-properties${buildQuery({ object_type: objectType, include_hidden: includeHidden })}`
  );
}

/** Every CRM object type this portal could plausibly extract from -- fixed
 * standard objects, plus this portal's custom objects when available. Needs
 * no input, unlike fetchHubspotAvailableProperties. */
export function fetchHubspotAvailableObjectTypes(): Promise<{ items: AvailableProperty[] }> {
  return apiGet<{ items: AvailableProperty[] }>("/meta/hubspot-tables/available-object-types");
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

export type UpdateBcTableInput = CreateBcTableInput;

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

export function fetchBcAvailableOdataTables(): Promise<{ items: AvailableProperty[] }> {
  return apiGet<{ items: AvailableProperty[] }>("/meta/bc-tables/available-odata-tables");
}

export function fetchBcAvailableCustomApiTables(): Promise<{ items: AvailableProperty[] }> {
  return apiGet<{ items: AvailableProperty[] }>("/meta/bc-tables/available-custom-api-tables");
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

export type UpdateFactorialTableInput = CreateFactorialTableInput;

export function updateFactorialTable(name: string, input: UpdateFactorialTableInput): Promise<FactorialTableConfig> {
  return apiPatch<FactorialTableConfig>(`/meta/factorial-tables/${encodeURIComponent(name)}`, input);
}

export function deleteFactorialTable(name: string): Promise<void> {
  return apiDelete<void>(`/meta/factorial-tables/${encodeURIComponent(name)}`);
}

/** Live "peek" at a Factorial endpoint's real data to suggest field names --
 * Factorial has no schema/properties endpoint like HubSpot's, so results
 * come from sampling actual records and may miss rarely-populated fields. */
export function fetchFactorialAvailableFields(path: string, dateRange = false): Promise<{ items: AvailableProperty[] }> {
  return apiGet<{ items: AvailableProperty[] }>(
    `/meta/factorial-tables/available-fields${buildQuery({ path, date_range: dateRange })}`
  );
}

/** Live discovery of every readable endpoint in Factorial's public API --
 * unlike fetchFactorialAvailableFields, this needs no input: Factorial
 * publishes its full OpenAPI spec at a stable, self-contained URL. */
export function fetchFactorialAvailableTables(): Promise<{ items: AvailableProperty[] }> {
  return apiGet<{ items: AvailableProperty[] }>("/meta/factorial-tables/available-tables");
}
