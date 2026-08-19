/**
 * Centralized, typed API client. Every request includes credentials (the
 * HttpOnly session cookie FastAPI's /auth/login sets) and every error path
 * throws a typed ApiError instead of leaving callers to guess at shapes.
 */

// Empty string (relative URL) by default: in production the API serves the
// built frontend itself (same origin), so requests should resolve against
// whatever host the browser loaded the page from, not a hardcoded one. Local
// dev sets VITE_API_BASE_URL explicitly (frontend/.env.example) since the
// Vite dev server and the API run on different ports there.
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function extractDetailMessage(detail: unknown): { message: string; code: string | undefined } {
  if (typeof detail === "string") {
    return { message: detail, code: undefined };
  }
  if (
    detail !== null &&
    typeof detail === "object" &&
    "message" in detail &&
    typeof (detail as { message: unknown }).message === "string"
  ) {
    const code = "code" in detail && typeof (detail as { code: unknown }).code === "string" ? (detail as { code: string }).code : undefined;
    return { message: (detail as { message: string }).message, code };
  }
  return { message: "Ha ocurrido un error inesperado.", code: undefined };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = payload !== null && typeof payload === "object" && "detail" in payload ? (payload as { detail: unknown }).detail : null;
    const { message, code } = extractDetailMessage(detail);
    throw new ApiError(response.status, message, code);
  }

  return payload as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: object): Promise<T> {
  return request<T>(path, { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) });
}

export function apiPatch<T>(path: string, body?: object): Promise<T> {
  return request<T>(path, { method: "PATCH", ...(body ? { body: JSON.stringify(body) } : {}) });
}

export function apiPut<T>(path: string, body?: object): Promise<T> {
  return request<T>(path, { method: "PUT", ...(body ? { body: JSON.stringify(body) } : {}) });
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

/** Absolute URL for a plain browser navigation (e.g. an <a href>-triggered
 * file download) that still needs the same base URL fetch()-based calls use.
 * The session cookie rides along automatically -- no fetch() wrapper needed. */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export type QueryValue = string | number | boolean | undefined | string[];

/** Builds a query string, repeating the key for array values (`action=a&action=b`)
 * to match FastAPI's `Query(default=[])` list-parameter convention. */
export function buildQuery(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params) as [string, QueryValue][]) {
    if (value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, item);
    } else {
      search.append(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}
