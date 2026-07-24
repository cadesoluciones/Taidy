import { useAuth } from "../auth/AuthContext";

/**
 * Placeholder landing page -- proves the full auth round trip (browser ->
 * Vite -> FastAPI -> users_db -> SQLite -> authenticated shell). The real
 * "Inicio" dashboard (metric tiles, quick links) lands once GET
 * /dashboard/summary exists on the API side -- see MIGRATION_PLAN.md, F-05.
 * Deliberately not mocked with fake numbers in the meantime.
 */
export function HomePage() {
  const { user } = useAuth();

  return (
    <section>
      <h1>Bienvenido, {user?.username}</h1>
      <p>
        Sesión iniciada con el rol <strong>{user?.role}</strong>. El resumen de actividad (tareas en
        curso, programaciones activas, historial reciente) se conectará aquí en la siguiente porción de
        la migración.
      </p>
    </section>
  );
}
