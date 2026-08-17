import { apiGet, apiPatch, apiPost } from "./client";

export interface EnvField {
  key: string;
  label: string;
  group: string;
  secret: boolean;
  value: string;
}

export interface TestConnectionResult {
  ok: boolean;
  message: string;
}

export function fetchSecrets(): Promise<{ items: EnvField[] }> {
  return apiGet<{ items: EnvField[] }>("/admin/secrets");
}

export function updateSecret(key: string, value: string): Promise<EnvField> {
  return apiPatch<EnvField>(`/admin/secrets/${encodeURIComponent(key)}`, { value });
}

export function testBusinessCentral(): Promise<TestConnectionResult> {
  return apiPost<TestConnectionResult>("/admin/secrets/test/business-central");
}

export function testFactorial(): Promise<TestConnectionResult> {
  return apiPost<TestConnectionResult>("/admin/secrets/test/factorial");
}

export function testHubspot(): Promise<TestConnectionResult> {
  return apiPost<TestConnectionResult>("/admin/secrets/test/hubspot");
}

export function testFabric(): Promise<TestConnectionResult> {
  return apiPost<TestConnectionResult>("/admin/secrets/test/fabric");
}
