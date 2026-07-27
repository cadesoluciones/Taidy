import { Link } from "react-router-dom";

import { fetchTasks } from "../api/tasks";
import { fetchWorkflowRuns } from "../api/workflows";
import { usePolling } from "../hooks/usePolling";
import { StatusBadge } from "./StatusBadge";
import styles from "./RunningActivityPreview.module.css";

/** Compact Inicio preview of what's running right now -- both plain tasks
 * and workflow runs, the same two sources /dashboard/summary's running_count
 * already adds together. Links out to the full Tareas en curso page for
 * management (stop, step detail); this is a glance, not a control panel. */
export function RunningActivityPreview() {
  const { data: tasksData } = usePolling(() => fetchTasks({ status: ["running"] }), 5000);
  const { data: runsData } = usePolling(() => fetchWorkflowRuns(), 5000);

  const runningTasks = tasksData?.items ?? [];
  const runningWorkflows = (runsData?.items ?? []).filter((r) => r.status === "running");
  const hasAny = runningTasks.length > 0 || runningWorkflows.length > 0;

  return (
    <div className={styles.panel}>
      <div className={styles.heading}>Tareas en curso</div>
      {!hasAny ? (
        <p className={styles.empty}>No hay ninguna tarea en curso ahora mismo.</p>
      ) : (
        <ul className={styles.list}>
          {runningTasks.map((t) => (
            <li key={t.id} className={styles.row}>
              <span className={styles.rowLabel}>{t.action_label}</span>
              <span className={styles.rowMeta}>
                {t.triggered_by} · {t.duration_seconds.toFixed(0)}s
              </span>
              <StatusBadge status={t.status} />
            </li>
          ))}
          {runningWorkflows.map((r) => (
            <li key={r.id} className={styles.row}>
              <span className={styles.rowLabel}>Flujo: {r.workflow_name}</span>
              <span className={styles.rowMeta}>
                {r.triggered_by} · {r.duration_seconds.toFixed(0)}s
              </span>
              <StatusBadge status={r.status} />
            </li>
          ))}
        </ul>
      )}
      <Link to="/actividad/tareas-en-curso" className={styles.link}>
        Ver todas →
      </Link>
    </div>
  );
}
