import { apiGet, apiPost } from "./client";

export const ROLE_READER = "App.Reader";
export const ROLE_OPERATOR = "App.Operator";
export const ROLE_ADMIN = "App.Admin";

export type Role = typeof ROLE_READER | typeof ROLE_OPERATOR | typeof ROLE_ADMIN;

export interface UserSession {
  username: string;
  role: Role;
  must_change_password: boolean;
}

export function login(username: string, password: string): Promise<UserSession> {
  return apiPost<UserSession>("/auth/login", { username, password });
}

export function logout(): Promise<void> {
  return apiPost<void>("/auth/logout");
}

export function fetchCurrentSession(): Promise<UserSession> {
  return apiGet<UserSession>("/auth/me");
}

export function changePassword(newPassword: string, confirmPassword: string): Promise<UserSession> {
  return apiPost<UserSession>("/auth/change-password", {
    new_password: newPassword,
    confirm_password: confirmPassword,
  });
}
