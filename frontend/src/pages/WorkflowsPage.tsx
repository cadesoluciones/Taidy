import { useEffect, useState } from "react";

import { ROLE_ADMIN, ROLE_OPERATOR } from "../api/auth";
import { ApiError } from "../api/client";
import {
  createWorkflow,
  deleteWorkflow,
  fetchWorkflowRuns,
  fetchWorkflows,
  runWorkflow,
  stopWorkflowRun,
  type StepDefinition,
  type Workflow,
  type WorkflowRun,
} from "../api/workflows";
import { useAuth } from "../auth/AuthContext";
import { ConfirmDialog } from "../components/ConfirmDialog";
import formStyles from "../components/Form.module.css";
import { StatusBadge } from "../components/StatusBadge";
import { usePolling } from "../hooks/usePolling";
import styles from "./WorkflowsPage.module.css";

const ACTION_LABELS: Record<string, string> = {
  extract_bc: "BC · Extraer",
  upload_bc: "BC · Subir",
  sync_bc: "BC · Sync (extraer + subir)",
  extract_factorial: "Factorial · Extraer",
  upload_factorial: "Factorial · Subir",
  sync_factorial: "Factorial · Sync (extraer + subir)",
  run_pipeline: "Fabric · Ejecutar pipeline",
};

/**
 * Baseline parity with webapp/app.py:page_workflows -- form-based designer +
 * saved/running lists. The interactive click-to-edit diagram (React Flow /
 * Cytoscape.js) is a deliberate follow-up upgrade, not a parity prerequisite
 * (see ARCHITECTURE.md, "Flujos (workflow designer)"); this pass represents
 * each run's steps as a plain status list instead of a graph.
 */
export function WorkflowsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === ROLE_ADMIN;
  const canOperate = user?.role === ROLE_ADMIN || user?.role === ROLE_OPERATOR;

  const [draftSteps, setDraftSteps] = useState<StepDefinition[]>([]);
  const [stepLabel, setStepLabel] = useState("");
  const [stepAction, setStepAction] = useState("extract_bc");
  const [dependsOn, setDependsOn] = useState<string[]>([]);
  const [triggerRule, setTriggerRule] = useState<"all_success" | "always">("all_success");
  const [workflowName, setWorkflowName] = useState("");
  const [designerError, setDesignerError] = useState<string | null>(null);

  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [pendingDeleteWorkflow, setPendingDeleteWorkflow] = useState<Workflow | null>(null);
  const [pendingStopRun, setPendingStopRun] = useState<WorkflowRun | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);

  const { data: runsData } = usePolling(() => fetchWorkflowRuns(), 3000);
  const runs = runsData?.items ?? [];

  async function reloadWorkflows() {
    setWorkflows((await fetchWorkflows()).items);
  }

  useEffect(() => {
    void reloadWorkflows();
  }, []);

  function addStep() {
    setDesignerError(null);
    const label = stepLabel.trim() || ACTION_LABELS[stepAction] || stepAction;
    if (draftSteps.some((s) => s.label === label)) {
      setDesignerError(`Ya hay un bloque con la etiqueta '${label}' en este borrador.`);
      return;
    }
    const id = `step_${Math.random().toString(36).slice(2, 10)}`;
    const dependsOnIds = dependsOn.map((depLabel) => draftSteps.find((s) => s.label === depLabel)?.id).filter(
      (v): v is string => Boolean(v),
    );
    setDraftSteps((prev) => [
      ...prev,
      { id, label, action: stepAction, params: {}, depends_on: dependsOnIds, trigger_rule: dependsOnIds.length ? triggerRule : "all_success" },
    ]);
    setStepLabel("");
    setDependsOn([]);
  }

  function removeStep(id: string) {
    setDraftSteps((prev) => prev.filter((s) => s.id !== id));
  }

  async function saveWorkflow(e: React.FormEvent) {
    e.preventDefault();
    setDesignerError(null);
    try {
      await createWorkflow(workflowName, draftSteps);
      setDraftSteps([]);
      setWorkflowName("");
      await reloadWorkflows();
    } catch (err) {
      setDesignerError(err instanceof ApiError ? err.message : "No se pudo guardar el flujo.");
    }
  }

  async function launchWorkflow(id: string) {
    setLaunchError(null);
    try {
      await runWorkflow(id);
    } catch (err) {
      setLaunchError(err instanceof ApiError ? err.message : "No se pudo lanzar el flujo.");
    }
  }

  async function confirmDeleteWorkflow() {
    if (!pendingDeleteWorkflow) return;
    setIsBusy(true);
    try {
      await deleteWorkflow(pendingDeleteWorkflow.id);
      await reloadWorkflows();
    } finally {
      setIsBusy(false);
      setPendingDeleteWorkflow(null);
    }
  }

  async function confirmStopRun() {
    if (!pendingStopRun) return;
    setIsBusy(true);
    try {
      await stopWorkflowRun(pendingStopRun.id);
    } finally {
      setIsBusy(false);
      setPendingStopRun(null);
    }
  }

  return (
    <section>
      <h1>Flujos</h1>
      <p>
        Compón un flujo añadiendo bloques uno a uno. Un bloque sin "depende de" se lanza en paralelo con los demás
        bloques sin dependencias; uno con dependencias espera a que todas terminen antes de decidir si se lanza.
      </p>

      {isAdmin ? (
        <>
          <h2>Diseñar un flujo nuevo</h2>
          {designerError && <div className={formStyles.errorBanner}>{designerError}</div>}
          <div className={formStyles.card}>
            <div className={formStyles.field}>
              <label htmlFor="step_label">Etiqueta del bloque</label>
              <input id="step_label" type="text" value={stepLabel} onChange={(e) => setStepLabel(e.target.value)} />
            </div>
            <div className={formStyles.field}>
              <label htmlFor="step_action">Acción del bloque</label>
              <select id="step_action" value={stepAction} onChange={(e) => setStepAction(e.target.value)}>
                {Object.entries(ACTION_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className={formStyles.field}>
              <label htmlFor="depends_on">Depende de</label>
              <select
                id="depends_on"
                multiple
                className={formStyles.multiselect}
                value={dependsOn}
                onChange={(e) => setDependsOn(Array.from(e.target.selectedOptions, (o) => o.value))}
              >
                {draftSteps.map((s) => (
                  <option key={s.id} value={s.label}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            {dependsOn.length > 0 && (
              <div className={formStyles.field}>
                <label htmlFor="trigger_rule">¿Cuándo lanzar este bloque?</label>
                <select
                  id="trigger_rule"
                  value={triggerRule}
                  onChange={(e) => setTriggerRule(e.target.value as "all_success" | "always")}
                >
                  <option value="all_success">Solo si todas sus dependencias tuvieron éxito</option>
                  <option value="always">Aunque alguna dependencia haya fallado</option>
                </select>
              </div>
            )}
            <button type="button" className={formStyles.submit} onClick={addStep}>
              Añadir bloque al flujo
            </button>
          </div>

          {draftSteps.length > 0 && (
            <>
              <h3>Bloques del borrador actual</h3>
              {draftSteps.map((s) => {
                const depLabels = draftSteps.filter((d) => s.depends_on.includes(d.id)).map((d) => d.label);
                return (
                  <div className={styles.stepRow} key={s.id}>
                    <strong>{s.label}</strong>
                    <span className={styles.stepMeta}>
                      ({ACTION_LABELS[s.action]}) — {depLabels.length ? `depende de: ${depLabels.join(", ")}` : "sin dependencias"}
                    </span>
                    <button type="button" className={styles.removeBtn} onClick={() => removeStep(s.id)}>
                      Quitar
                    </button>
                  </div>
                );
              })}
              <form className={formStyles.card} onSubmit={saveWorkflow} style={{ marginTop: 12 }}>
                <div className={formStyles.field}>
                  <label htmlFor="workflow_name">Nombre del flujo</label>
                  <input
                    id="workflow_name"
                    type="text"
                    value={workflowName}
                    onChange={(e) => setWorkflowName(e.target.value)}
                  />
                </div>
                <button type="submit" className={formStyles.submit}>
                  Guardar flujo
                </button>
                <button type="button" className={styles.btn} style={{ marginLeft: 8 }} onClick={() => setDraftSteps([])}>
                  Descartar borrador
                </button>
              </form>
            </>
          )}
        </>
      ) : (
        <p>Diseñar o borrar flujos requiere el rol App.Admin. Puedes consultarlos y lanzarlos abajo.</p>
      )}

      <h2>Flujos guardados</h2>
      {launchError && <div className={formStyles.errorBanner}>{launchError}</div>}
      {workflows.length === 0 ? (
        <p>Todavía no hay flujos guardados.</p>
      ) : (
        workflows.map((wf) => (
          <div className={styles.workflowCard} key={wf.id}>
            <div className={styles.workflowHead}>
              <strong>{wf.name}</strong>
              <span className={styles.stepMeta}>{wf.steps.length} bloque(s)</span>
              {canOperate && (
                <button type="button" className={styles.btnPrimary} onClick={() => void launchWorkflow(wf.id)}>
                  Lanzar flujo
                </button>
              )}
              {isAdmin && (
                <button type="button" className={styles.btnDanger} onClick={() => setPendingDeleteWorkflow(wf)}>
                  Borrar flujo
                </button>
              )}
            </div>
            {wf.steps.map((s) => (
              <div key={s.id} className={styles.stepMeta}>
                {s.label} ({ACTION_LABELS[s.action] ?? s.action})
                {s.depends_on.length > 0 && ` — depende de ${s.depends_on.length} bloque(s)`}
              </div>
            ))}
          </div>
        ))
      )}

      <h2>Flujos en curso / recientes</h2>
      {runs.length === 0 ? (
        <p>No hay ejecuciones de flujos en esta sesión del servidor.</p>
      ) : (
        runs.map((run) => {
          const canStop =
            run.status === "running" && (user?.role === ROLE_ADMIN || run.triggered_by === user?.username);
          return (
            <div className={styles.workflowCard} key={run.id}>
              <div className={styles.workflowHead}>
                <strong>{run.workflow_name}</strong>
                <span className={styles.stepMeta}>
                  {run.triggered_by} · {run.duration_seconds.toFixed(0)}s
                </span>
                <StatusBadge status={run.status} />
                {run.status === "running" && (
                  <button
                    type="button"
                    className={styles.btnDanger}
                    disabled={!canStop}
                    onClick={() => setPendingStopRun(run)}
                  >
                    Detener flujo
                  </button>
                )}
              </div>
              {run.steps.map((s) => (
                <div key={s.id} className={styles.stepMeta}>
                  {s.label} — <StatusBadge status={s.status} />
                </div>
              ))}
            </div>
          );
        })
      )}

      <ConfirmDialog
        open={pendingDeleteWorkflow !== null}
        title="Borrar flujo"
        description={`Vas a borrar el flujo "${pendingDeleteWorkflow?.name}" y su definición completa. Las tareas programadas que lo usen dejarán de funcionar. Esta acción no se puede deshacer.`}
        confirmLabel="Borrar definitivamente"
        busy={isBusy}
        onConfirm={confirmDeleteWorkflow}
        onCancel={() => setPendingDeleteWorkflow(null)}
      />
      <ConfirmDialog
        open={pendingStopRun !== null}
        title="Detener flujo"
        description={`Vas a detener el flujo "${pendingStopRun?.workflow_name}" en curso. El bloque que esté ejecutándose se interrumpe y los bloques pendientes no se lanzarán.`}
        confirmLabel="Detener definitivamente"
        busy={isBusy}
        onConfirm={confirmStopRun}
        onCancel={() => setPendingStopRun(null)}
      />
    </section>
  );
}
