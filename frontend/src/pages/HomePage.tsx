import { Link } from "react-router-dom";
import { Activity, AlertTriangle, CalendarClock, type LucideIcon } from "lucide-react";

import { fetchDashboardSummary } from "../api/dashboard";
import { useAuth } from "../auth/AuthContext";
import { DataNetworkArt } from "../components/DataNetworkArt";
import { OutcomeIcon } from "../components/OutcomeIcon";
import { Timeline, type TimelineItem } from "../components/Timeline";
import { usePolling } from "../hooks/usePolling";
import styles from "./HomePage.module.css";

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

  const errorCount = summary?.recent_error_count ?? 0;
  const runningCount = summary?.running_count ?? 0;
  let statusTone: "success" | "warning" | "info" = "success";
  let statusMessage = "Operación normal, sin incidencias recientes.";
  if (errorCount > 0) {
    statusTone = "warning";
    statusMessage = `Atención: ${errorCount} error${errorCount === 1 ? "" : "es"} reciente${errorCount === 1 ? "" : "s"}.`;
  } else if (runningCount > 0) {
    statusTone = "info";
    statusMessage = `${runningCount} tarea${runningCount === 1 ? "" : "s"} en curso ahora mismo.`;
  }

  return (
    <section>
      <div className={styles.heroRow}>
        <div className={styles.hero}>
          <DataNetworkArt className={styles.heroArt} />
          <div className={styles.heroContent}>
            <div className={styles.heroEyebrow}>Panel de datos</div>
            <h1 className={styles.heroTitle}>Taidy — Panel de datos</h1>
            <p className={styles.heroSubtitle}>
              Extracción y carga al datalake de Business Central y Factorial HR, sin depender de la terminal.
            </p>
          </div>
        </div>

        <div className={styles.tiles}>
          <Metric icon={Activity} label="Tareas en curso" value={summary?.running_count} />
          <Metric icon={CalendarClock} label="Programadas activas" value={summary?.active_schedule_count} />
          <Metric icon={AlertTriangle} label="Errores recientes" value={summary?.recent_error_count} />
        </div>

        <div className={styles.accentCard}>
          <div className={styles.accentEyebrow}>Programación</div>
          <h3 className={styles.accentTitle}>Tareas programadas activas</h3>
          <div className={styles.accentValue}>{summary?.active_schedule_count ?? "—"}</div>
          <Link to="/programacion" className={styles.accentLink}>
            Ver programación →
          </Link>
        </div>
      </div>

      {summary && (
        <div className={`${styles.statusBar} ${styles[statusTone]}`}>
          <span className={styles.statusDot} aria-hidden="true" />
          <strong>Estado del sistema:</strong> {statusMessage}
        </div>
      )}

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
      <Timeline
        emptyLabel="Todavía no se ha ejecutado ninguna tarea."
        items={(summary?.recent_history ?? []).map(
          (entry, i): TimelineItem => ({
            key: `${entry.finished_at}-${i}`,
            icon: <OutcomeIcon ok={entry.ok} status={entry.status} />,
            tone: entry.ok ? "success" : entry.status === "stopped" ? "neutral" : "danger",
            title: (
              <>
                {entry.action} <span className={styles.entrySource}>— {entry.source}</span>
              </>
            ),
            timestamp: entry.finished_at,
          }),
        )}
      />

      <p className={styles.sessionNote}>
        Sesión iniciada como {user?.username} ({user?.role}).
      </p>
    </section>
  );
}

function Metric({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: number | undefined }) {
  return (
    <div className={styles.tile}>
      <Icon size={20} className={styles.tileIcon} aria-hidden="true" />
      <div>
        <div className={styles.tileValue}>{value ?? "—"}</div>
        <div className={styles.tileLabel}>{label}</div>
      </div>
    </div>
  );
}
