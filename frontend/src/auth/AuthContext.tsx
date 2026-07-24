import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import * as authApi from "../api/auth";
import type { UserSession } from "../api/auth";

interface AuthContextValue {
  user: UserSession | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (newPassword: string, confirmPassword: string) => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserSession | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const session = await authApi.fetchCurrentSession();
      setUser(session);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setUser(null);
      } else {
        throw error;
      }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    refresh().finally(() => {
      if (!cancelled) {
        setIsLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const session = await authApi.login(username, password);
    setUser(session);
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
  }, []);

  const changePassword = useCallback(async (newPassword: string, confirmPassword: string) => {
    const session = await authApi.changePassword(newPassword, confirmPassword);
    setUser(session);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, login, logout, changePassword, refresh }),
    [user, isLoading, login, logout, changePassword, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
