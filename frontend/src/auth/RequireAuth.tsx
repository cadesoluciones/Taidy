import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "./AuthContext";

/**
 * No session -> the login page; a pending forced password change -> the
 * change-password page, blocking everything else. The server re-checks all
 * of this on every request regardless -- this guard is UX only, never the
 * real authorization boundary (see api/dependencies.py).
 */
export function RequireAuth() {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return null;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (user.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }

  return <Outlet />;
}

export function RedirectIfAuthenticated({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return null;
  }

  if (user && !user.must_change_password) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
