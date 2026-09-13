import { apiGet, apiPatch, apiPut } from "./client";

export type ConfigFieldKind = "text" | "number" | "boolean" | "list";
export type ConfigFieldValue = string | number | boolean | string[];

export interface ConfigField {
  key: string;
  label: string;
  group: string;
  kind: ConfigFieldKind;
  value: ConfigFieldValue;
}

export interface Pipeline {
  name: string;
  item_id: string;
}

/** Non-secret connection parameters from config.json (tenant/client/
 * workspace/lakehouse ids, retry/paging tuning, notifications) -- see
 * webapp/config_settings.py. Sits alongside /admin/secrets (the actual
 * secrets, from .env) in the same "Claves de servicio" screen. */
export function fetchConfigFields(): Promise<{ items: ConfigField[] }> {
  return apiGet<{ items: ConfigField[] }>("/admin/config");
}

export function updateConfigField(key: string, value: ConfigFieldValue): Promise<ConfigField> {
  return apiPatch<ConfigField>(`/admin/config/${encodeURIComponent(key)}`, { value });
}

export function fetchPipelines(): Promise<{ items: Pipeline[] }> {
  return apiGet<{ items: Pipeline[] }>("/admin/config/pipelines");
}

export function setPipelines(items: Pipeline[]): Promise<{ items: Pipeline[] }> {
  return apiPut<{ items: Pipeline[] }>("/admin/config/pipelines", { items });
}
