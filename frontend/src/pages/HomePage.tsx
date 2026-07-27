import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertTriangle, CalendarClock, Sparkles, type LucideIcon } from "lucide-react";

import { ROLE_READER } from "../api/auth";
import { ApiError } from "../api/client";
import { fetchDashboardSummary, fetchNarrativeSummary, fetchSummaryMode } from "../api/dashboard";
import { useAuth } from "../auth/AuthContext";
import { ACTION_LABELS } from "../components/actionLabels";
import { DataNetworkArt } from "../components/DataNetworkArt";
import formStyles from "../components/Form.module.css";
import { OutcomeIcon } from "../components/OutcomeIcon";
import { RunningActivityPreview } from "../components/RunningActivityPreview";
import { Timeline, type TimelineItem } from "../components/Timeline";
import { WeeklyScheduleCalendar } from "../components/WeeklyScheduleCalendar";
import { usePolling } from "../hooks/usePolling";
import styles from "./HomePage.module.css";
import { ReaderHomePage } from "./ReaderHomePage";

export function HomePage() {
  const { user } = useAuth();
  // Reader's Inicio is a different page entirely -- launch/follow their
  // assigned workflow(s), nothing about tasks/schedules/checkpoints. The
  // dashboard-polling hooks below are only safe to call for Admin/Operator,
  // so they live in their own component rather than being called
  // conditionally in this one.
  if (user?.role === ROLE_READER) {
    return <ReaderHomePage />;
  }
  return <AdminOperatorHomePage />;
}

function AdminOperatorHomePage() {
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

  // A cheap fingerprint of "did something worth re-summarizing just happen":
  // the most recent history entry's identity, plus the current set of
  // error-rate alerts. Recomputed every 10s poll tick (same cadence as
  // `summary` itself) but only changes value when the underlying activity
  // actually changes, which is what triggers ActivitySummaryCard's effect.
  const latestEntry = summary?.recent_history[0];
  const changeSignature = summary
    ? JSON.stringify([latestEntry?.finished_at, latestEntry?.action, latestEntry?.source, summary.error_rate_alerts])
    : "";

  return (
    <section>
      <div className={styles.heroRow}>
        <div className={styles.hero}>
          <DataNetworkArt className={styles.heroArt} />
          <div className={styles.heroContent}>
            <div className={styles.heroEyebrow}>Panel de datos</div>
            <h1 className={styles.heroTitle}>NEXUS-BDB — Panel de datos</h1>
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

      {summary && summary.error_rate_alerts.length > 0 && (
        <div className={styles.alertsBox}>
          <div className={styles.alertsHeading}>
            <AlertTriangle size={16} />
            Tasa de errores elevada
          </div>
          <ul className={styles.alertsList}>
            {summary.error_rate_alerts.map((a) => (
              <li key={a.action}>
                <strong>{ACTION_LABELS[a.action] ?? a.action}</strong>: {a.recent_failures} de {a.recent_total}{" "}
                ejecuciones recientes han fallado.
              </li>
            ))}
          </ul>
        </div>
      )}

      <ActivitySummaryCard changeSignature={changeSignature} />

      <div className={styles.midRow}>
        <div>
          <h2>Tareas en curso</h2>
          <RunningActivityPreview />
        </div>
        <div>
          <h2>Esta semana</h2>
          <WeeklyScheduleCalendar />
        </div>
      </div>

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

/** Auto-regenerates whenever `changeSignature` changes (a new run finished,
 * an error-rate alert appeared/cleared) instead of requiring a manual click
 * -- an admin-configured mode (Administración > Configuración) decides
 * whether that's a free template or an LLM call; either way this always has
 * something to show (the LLM path falls back to the template server-side,
 * reflected in modeUsed/llmProvider below). */
function ActivitySummaryCard({ changeSignature }: { changeSignature: string }) {
  const [text, setText] = useState<string | null>(null);
  const [modeUsed, setModeUsed] = useState<"template" | "llm" | null>(null);
  const [configuredMode, setConfiguredMode] = useState<"template" | "llm" | null>(null);
  const [llmProvider, setLlmProvider] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setIsLoading(true);
    setError(null);
    try {
      const [result, configured] = await Promise.all([fetchNarrativeSummary(), fetchSummaryMode()]);
      setText(result.text);
      setModeUsed(result.mode_used);
      setLlmProvider(result.llm_provider);
      setConfiguredMode(configured.mode);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo generar el resumen.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (changeSignature) void generate();
    // Only re-run when the underlying activity actually changed, not on
    // every 10s poll tick that leaves changeSignature unchanged.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [changeSignature]);

  return (
    <div className={styles.summaryCard}>
      <div className={styles.summaryHeading}>
        <Sparkles size={16} />
        Resumen de actividad
        <button
          type="button"
          className={styles.summaryRefreshBtn}
          disabled={isLoading}
          onClick={() => void generate()}
        >
          {isLoading ? "Actualizando…" : "Actualizar"}
        </button>
      </div>
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {text && (
        <div className={styles.summaryText}>
          <p>{text}</p>
          {modeUsed === "llm" && llmProvider && (
            <p className={styles.summaryFallbackNote}>Generado con {llmProvider}.</p>
          )}
          {configuredMode === "llm" && modeUsed === "template" && (
            <p className={styles.summaryFallbackNote}>
              La IA generativa está configurada (Administración &gt; Configuración) pero no está disponible ahora
              mismo; se muestra el resumen por plantilla.
            </p>
          )}
        </div>
      )}
    </div>
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
