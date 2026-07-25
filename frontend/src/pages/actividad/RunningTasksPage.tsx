import { useState } from "react";

import { ROLE_ADMIN } from "../../api/auth";
import { fetchTasks, stopTask, type Task } from "../../api/tasks";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { StatusBadge } from "../../components/StatusBadge";
import { StepStatusGrid } from "../../components/StepStatusGrid";
import { usePolling } from "../../hooks/usePolling";
import styles from "./RunningTasksPage.module.css";

export function RunningTasksPage() {
  const { user } = useAuth();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [confirmingStop, setConfirmingStop] = useState<Task | null>(null);
  const [isStopping, setIsStopping] = useState(false);

  const { data, error } = usePolling(() => fetchTasks(), 5000);
  const tasks = data?.items ?? [];

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function confirmStop() {
    if (!confirmingStop) return;
    setIsStopping(true);
    try {
      await stopTask(confirmingStop.id);
    } finally {
      setIsStopping(false);
      setConfirmingStop(null);
    }
  }

  return (
    <section>
      <h1>Tareas en curso</h1>
      {error && <p>No se pudo actualizar la lista de tareas.</p>}
      {tasks.length === 0 ? (
        <p className={styles.emptyState}>No hay tareas registradas en esta sesión del servidor.</p>
      ) : (
        <div className={styles.list}>
          {tasks.map((task) => {
            const canStop =
              task.status === "running" && (user?.role === ROLE_ADMIN || task.triggered_by === user?.username);
            const stepInfo =
              task.step_labels.length > 1
                ? ` · paso ${Math.min(task.current_step + 1, task.step_labels.length)}/${task.step_labels.length}: ${task.step_labels[task.current_step]}`
                : "";
            return (
              <div key={task.id} className={styles.row}>
                <div className={styles.rowMain}>
                  <strong>{task.action_label}</strong>
                  <span className={styles.rowMeta}>
                    {task.triggered_by} · {task.duration_seconds.toFixed(0)}s{stepInfo}
                  </span>
                </div>
                <div className={styles.rowActions}>
                  <StatusBadge status={task.status} />
                  <button
                    type="button"
                    className={styles.stopButton}
                    disabled={!canStop}
                    onClick={() => setConfirmingStop(task)}
                  >
                    Detener
                  </button>
                  <button type="button" className={styles.toggle} onClick={() => toggle(task.id)}>
                    {expanded.has(task.id) ? "Ocultar" : "Ver"}
                  </button>
                </div>
                {expanded.has(task.id) && task.table_statuses.length > 0 && (
                  <div className={styles.expanded}>
                    <StepStatusGrid items={task.table_statuses} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={confirmingStop !== null}
        title="Detener tarea"
        description={`Vas a detener la tarea "${confirmingStop?.action_label}" en curso. Si estaba escribiendo datos, se interrumpirá en el punto en el que esté.`}
        confirmLabel="Detener definitivamente"
        busy={isStopping}
        onConfirm={confirmStop}
        onCancel={() => setConfirmingStop(null)}
      />
    </section>
  );
}
