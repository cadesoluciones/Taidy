import { Navigate, Outlet } from "react-router-dom";

import { ROLE_ADMIN } from "../api/auth";
import { useAuth } from "./AuthContext";

/** UI-only convenience; the API re-checks the role on every request
 * regardless (see api/dependencies.py:require_role) -- this just avoids
 * showing an Admin-only page to someone who'll get 403s from every call. */
export function RequireAdmin() {
  const { user } = useAuth();
  if (user?.role !== ROLE_ADMIN) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
