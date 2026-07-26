import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type { Role } from "./auth";

export interface ManagedUser {
  username: string;
  role: Role;
  must_change_password: boolean;
  locked_until: string | null;
}

export function fetchUsers(): Promise<{ items: ManagedUser[] }> {
  return apiGet<{ items: ManagedUser[] }>("/users");
}

export function createUser(username: string, password: string, role: Role): Promise<ManagedUser> {
  return apiPost<ManagedUser>("/users", { username, password, role });
}

export function changeUserRole(username: string, role: Role): Promise<ManagedUser> {
  return apiPatch<ManagedUser>(`/users/${encodeURIComponent(username)}/role`, { role });
}

export function resetUserPassword(username: string): Promise<void> {
  return apiPost<void>(`/users/${encodeURIComponent(username)}/reset-password`);
}

export function deleteUser(username: string): Promise<void> {
  return apiDelete<void>(`/users/${encodeURIComponent(username)}`);
}

export interface UserSession {
  session_ref: string;
  created_at: string;
}

export function fetchUserSessions(username: string): Promise<{ items: UserSession[] }> {
  return apiGet<{ items: UserSession[] }>(`/users/${encodeURIComponent(username)}/sessions`);
}

export function revokeUserSession(username: string, sessionRef: string): Promise<void> {
  return apiDelete<void>(`/users/${encodeURIComponent(username)}/sessions/${encodeURIComponent(sessionRef)}`);
}
