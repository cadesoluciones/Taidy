import { Link } from "react-router-dom";

import { fetchDashboardSummary } from "../api/dashboard";
import { useAuth } from "../auth/AuthContext";
import { usePolling } from "../hooks/usePolling";

const QUICK_LINKS = [
  { to: "/ejecutar/bc-sync", label: "Business Central · Sync" },
  { to: "/ejecutar/bc-extraer", label: "Business Central · Extraer" },
  { to: "/ejecutar/factorial-sync", label: "Factorial · Sync" },
  { to: "/ejecutar/pipelines", label: "Fabric · Pipelines" },
  { to: "/flujos", label: "Flujos" },
  { to: "/programacion", label: "Tareas programadas" },
];

export function HomePage() {
  const { user } = useAuth();
  const { data: summary } = usePolling(fetchDashboardSummary, 10000);

  return (
    <section>
      <h1>Taidy — Panel de datos</h1>
      <p>Extracción y carga al datalake de Business Central y Factorial HR, sin depender de la terminal.</p>

      <div style={{ display: "flex", gap: 24, margin: "16px 0" }}>
        <Metric label="Tareas en curso" value={summary?.running_count} />
        <Metric label="Tareas programadas activas" value={summary?.active_schedule_count} />
        <Metric label="Errores recientes" value={summary?.recent_error_count} />
      </div>

      <h2>Accesos directos</h2>
      <ul>
        {QUICK_LINKS.map((link) => (
          <li key={link.to}>
            <Link to={link.to}>{link.label}</Link>
          </li>
        ))}
      </ul>

      <h2>Actividad reciente</h2>
      <p>
        <Link to="/actividad/tareas-en-curso">Ver tareas en curso</Link> ·{" "}
        <Link to="/actividad/historial">Ver historial completo</Link>
      </p>
      {!summary?.recent_history.length ? (
        <p>Todavía no se ha ejecutado ninguna tarea.</p>
      ) : (
        summary.recent_history.map((entry, i) => (
          <div key={i}>
            {entry.ok ? "✅" : entry.status === "stopped" ? "⏹️" : "❌"} <strong>{entry.action}</strong> —{" "}
            {entry.source} — {entry.finished_at}
          </div>
        ))
      )}

      <p style={{ marginTop: 32, color: "var(--color-text-muted)", fontSize: 13 }}>
        Sesión iniciada como {user?.username} ({user?.role}).
      </p>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      <div style={{ fontSize: 28, fontWeight: 700 }}>{value ?? "—"}</div>
      <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{label}</div>
    </div>
  );
}
