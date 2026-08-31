import { useState } from "react";

import { ApiError } from "../api/client";
import { fetchMyWorkflows } from "../api/dashboard";
import { runWorkflow } from "../api/workflows";
import { useAuth } from "../auth/AuthContext";
import { ACTION_LABELS } from "../components/actionLabels";
import formStyles from "../components/Form.module.css";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { WorkflowDiagram } from "../components/WorkflowDiagram";
import { usePolling } from "../hooks/usePolling";
import styles from "./ReaderHomePage.module.css";

/** Simplified Inicio for App.Reader users (e.g. one RRHH user, one Compras
 * user): each only sees the workflow(s) an admin assigned them
 * (webapp/workflows.reader_allowed_users), can launch one, and follows its
 * live progress here -- nothing else. No mention of tasks, schedules,
 * checkpoints, or any of the vocabulary the rest of the app uses; those
 * pages are hidden from this role's nav entirely (see NavShell/
 * RequireOperatorOrAdmin). */
export function ReaderHomePage() {
  const { user } = useAuth();
  const { data, error: pollError, refetch } = usePolling(fetchMyWorkflows, 3000);
  const [launchingId, setLaunchingId] = useState<string | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [launchSuccess, setLaunchSuccess] = useState<string | null>(null);

  const items = data?.items ?? [];

  async function handleLaunch(workflowId: string) {
    setLaunchError(null);
    setLaunchSuccess(null);
    setLaunchingId(workflowId);
    try {
      const run = await runWorkflow(workflowId);
      setLaunchSuccess(`Flujo lanzado (${run.id.slice(0, 8)}). Sigue el progreso abajo.`);
      // Otherwise the button would misleadingly fall back to "Lanzar" (not
      // yet disabled) for up to the full poll interval, since launching
      // itself resolves almost instantly but the next scheduled tick hasn't
      // run yet -- it looks settled when it's actually still starting up.
      await refetch();
    } catch (err) {
      setLaunchError(err instanceof ApiError ? err.message : "No se pudo lanzar el flujo.");
    } finally {
      setLaunchingId(null);
    }
  }

  return (
    <section>
      <PageHeader title="NEXUS-BDB — Panel de datos" />
      <p>Hola, {user?.username}. Aquí puedes lanzar y seguir tus flujos.</p>

      {pollError && <div className={formStyles.errorBanner}>No se pudo actualizar el estado. Reintentando…</div>}
      {launchSuccess && <div className={formStyles.successBanner}>{launchSuccess}</div>}
      {launchError && <div className={formStyles.errorBanner}>{launchError}</div>}

      {items.length === 0 ? (
        <p>Todavía no tienes ningún flujo asignado. Contacta con tu administrador.</p>
      ) : (
        items.map((wf) => {
          const run = wf.current_run ?? wf.last_run;
          const isRunning = wf.current_run !== null;
          return (
            <div className={styles.card} key={wf.id} data-testid="my-workflow-card">
              <div className={styles.cardHead}>
                <strong>{wf.name}</strong>
                {run ? <StatusBadge status={run.status} /> : <span className={styles.neverRun}>Nunca se ha ejecutado</span>}
                {wf.scheduled && <span className={styles.scheduledHint}>Se ejecuta automáticamente</span>}
                <button
                  type="button"
                  className={styles.launchBtn}
                  disabled={isRunning || launchingId === wf.id}
                  onClick={() => void handleLaunch(wf.id)}
                >
                  {isRunning ? "Ya en marcha" : launchingId === wf.id ? "Lanzando…" : "Lanzar"}
                </button>
              </div>
              {run && (
                <>
                  <p className={styles.runMeta}>
                    {isRunning ? "En curso desde" : "Última vez"} {new Date(run.started_at).toLocaleString("es-ES")}
                  </p>
                  <WorkflowDiagram
                    steps={run.steps}
                    actionLabels={ACTION_LABELS}
                    stepStatuses={Object.fromEntries(run.steps.map((s) => [s.id, s.status]))}
                    readOnly
                    height={180}
                  />
                </>
              )}
            </div>
          );
        })
      )}
    </section>
  );
}
