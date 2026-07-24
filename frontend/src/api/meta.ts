import { apiGet } from "./client";

export function fetchBcTables(): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>("/meta/bc-tables");
}

export function fetchFactorialTables(): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>("/meta/factorial-tables");
}

export function fetchPipelines(): Promise<{ items: string[] }> {
  return apiGet<{ items: string[] }>("/meta/pipelines");
}
