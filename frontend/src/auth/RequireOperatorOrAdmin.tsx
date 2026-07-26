import { Navigate, Outlet } from "react-router-dom";

import { ROLE_ADMIN, ROLE_OPERATOR } from "../api/auth";
import { useAuth } from "./AuthContext";

/** Reader's whole experience is the simplified Inicio (launch/follow their
 * assigned workflows) + Cuenta -- these operational pages (Ejecutar,
 * Flujos, Programación, Actividad) assume knowledge Reader isn't meant to
 * need. UI-only convenience; the API already gates every one of these
 * capabilities by role (and, for workflows, by per-workflow reader access)
 * regardless of what this guard does. */
export function RequireOperatorOrAdmin() {
  const { user } = useAuth();
  if (user?.role !== ROLE_ADMIN && user?.role !== ROLE_OPERATOR) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
