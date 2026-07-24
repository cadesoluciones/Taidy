import styles from "./StatusBadge.module.css";

/** One badge component for every status vocabulary the backend emits --
 * never invents a new client-side state (mirrors webapp/app.py's
 * _TASK_STATUS_BADGE / _TABLE_STATUS_LABELS dicts). */
const LABELS: Record<string, { label: string; tone: "info" | "warning" | "success" | "danger" | "neutral" }> = {
  running: { label: "En curso", tone: "info" },
  stopping: { label: "Deteniendo…", tone: "warning" },
  ok: { label: "Completada", tone: "success" },
  error: { label: "Error", tone: "danger" },
  stopped: { label: "Detenida", tone: "neutral" },
  pending: { label: "Pendiente", tone: "neutral" },
  cancelled: { label: "Cancelada", tone: "neutral" },
  skipped: { label: "Omitida", tone: "neutral" },
  dry_run: { label: "Simulada", tone: "warning" },
  unknown: { label: "Desconocido", tone: "neutral" },
  in_progress: { label: "En curso", tone: "info" },
};

export function StatusBadge({ status }: { status: string }) {
  const entry = LABELS[status] ?? { label: status, tone: "neutral" as const };
  return <span className={`${styles.badge} ${styles[entry.tone]}`}>{entry.label}</span>;
}
