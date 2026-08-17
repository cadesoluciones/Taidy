import { useEffect, useState } from "react";

import { ROLE_ADMIN, ROLE_OPERATOR, ROLE_READER } from "../api/auth";
import { ApiError } from "../api/client";
import { fetchPipelines } from "../api/meta";
import { fetchUsers } from "../api/users";
import {
  createWorkflow,
  deleteWorkflow,
  fetchWorkflowRuns,
  fetchWorkflows,
  retryWorkflowRun,
  runWorkflow,
  setWorkflowReaderAccess,
  stopWorkflowRun,
  updateWorkflow,
  type StepDefinition,
  type Workflow,
  type WorkflowRun,
} from "../api/workflows";
import { useAuth } from "../auth/AuthContext";
import { ACTION_LABELS } from "../components/actionLabels";
import { ConfirmDialog } from "../components/ConfirmDialog";
import formStyles from "../components/Form.module.css";
import { NotifyCheckbox } from "../components/NotifyCheckbox";
import { StatusBadge } from "../components/StatusBadge";
import { TagMultiSelect } from "../components/TagMultiSelect";
import { WorkflowDiagram } from "../components/WorkflowDiagram";
import { usePolling } from "../hooks/usePolling";
import styles from "./WorkflowsPage.module.css";

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
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [workflowName, setWorkflowName] = useState("");
  const [designerError, setDesignerError] = useState<string | null>(null);
  const [editingWorkflowId, setEditingWorkflowId] = useState<string | null>(null);

  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [pendingDeleteWorkflow, setPendingDeleteWorkflow] = useState<Workflow | null>(null);
  const [pendingStopRun, setPendingStopRun] = useState<WorkflowRun | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [notifyByWorkflow, setNotifyByWorkflow] = useState<Record<string, boolean>>({});
  const [readerUsernames, setReaderUsernames] = useState<string[]>([]);
  const [pipelines, setPipelines] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"saved" | "editor">("saved");
  const [newStepAction, setNewStepAction] = useState<string>("extract_bc");
  const [newStepPipeline, setNewStepPipeline] = useState<string>("");

  const { data: runsData, refetch: refetchRuns } = usePolling(() => fetchWorkflowRuns(), 3000);
  const runs = runsData?.items ?? [];
  const selectedStep = draftSteps.find((s) => s.id === selectedStepId) ?? null;

  async function reloadWorkflows() {
    setWorkflows((await fetchWorkflows()).items);
  }

  useEffect(() => {
    void reloadWorkflows();
  }, []);

  useEffect(() => {
    fetchPipelines()
      .then((res) => setPipelines(res.items))
      .catch(() => setPipelines([]));
  }, []);

  useEffect(() => {
    if (newStepAction === "run_pipeline" && !newStepPipeline && pipelines.length > 0) {
      setNewStepPipeline(pipelines[0] ?? "");
    }
  }, [pipelines, newStepAction, newStepPipeline]);

  useEffect(() => {
    if (!isAdmin) return;
    fetchUsers()
      .then((res) => setReaderUsernames(res.items.filter((u) => u.role === ROLE_READER).map((u) => u.username)))
      .catch(() => setReaderUsernames([]));
  }, [isAdmin]);

  async function handleSetReaderAccess(workflowId: string, usernames: string[]) {
    const updated = await setWorkflowReaderAccess(workflowId, usernames);
    setWorkflows((prev) => prev.map((w) => (w.id === workflowId ? updated : w)));
  }

  function addStep() {
    if (newStepAction === "run_pipeline" && !newStepPipeline) return;
    setDesignerError(null);
    const id = `step_${Math.random().toString(36).slice(2, 10)}`;
    const label = `Bloque ${draftSteps.length + 1}`;
    const params = newStepAction === "run_pipeline" ? { pipeline: newStepPipeline } : {};
    setDraftSteps((prev) => [
      ...prev,
      { id, label, action: newStepAction, params, depends_on: [], trigger_rule: "all_success" },
    ]);
    setSelectedStepId(id);
  }

  function updateStep(id: string, patch: Partial<StepDefinition>) {
    setDraftSteps((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }

  function removeStep(id: string) {
    setDraftSteps((prev) =>
      prev.filter((s) => s.id !== id).map((s) => ({ ...s, depends_on: s.depends_on.filter((d) => d !== id) })),
    );
    setSelectedStepId((cur) => (cur === id ? null : cur));
  }

  /** Client-side mirror of webapp/workflows.py:_validate_steps()'s cycle
   * check (Kahn's algorithm) -- lets the diagram reject a connection
   * immediately instead of waiting for a round trip to find out the save
   * would be rejected. */
  function wouldCreateCycle(steps: StepDefinition[]): boolean {
    const indegree = new Map(steps.map((s) => [s.id, 0]));
    const graph = new Map<string, string[]>(steps.map((s) => [s.id, []]));
    for (const s of steps) {
      for (const dep of s.depends_on) {
        graph.get(dep)?.push(s.id);
        indegree.set(s.id, (indegree.get(s.id) ?? 0) + 1);
      }
    }
    const queue = [...indegree.entries()].filter(([, d]) => d === 0).map(([id]) => id);
    let visited = 0;
    while (queue.length > 0) {
      const node = queue.pop() as string;
      visited += 1;
      for (const next of graph.get(node) ?? []) {
        indegree.set(next, (indegree.get(next) ?? 0) - 1);
        if (indegree.get(next) === 0) queue.push(next);
      }
    }
    return visited !== steps.length;
  }

  function connectSteps(sourceId: string, targetId: string) {
    setDesignerError(null);
    setDraftSteps((prev) => {
      const target = prev.find((s) => s.id === targetId);
      if (!target || target.depends_on.includes(sourceId)) return prev;
      const next = prev.map((s) => (s.id === targetId ? { ...s, depends_on: [...s.depends_on, sourceId] } : s));
      if (wouldCreateCycle(next)) {
        setDesignerError("Esa conexión crearía una dependencia circular entre bloques.");
        return prev;
      }
      return next;
    });
  }

  function removeDependency(sourceId: string, targetId: string) {
    setDraftSteps((prev) =>
      prev.map((s) => (s.id === targetId ? { ...s, depends_on: s.depends_on.filter((d) => d !== sourceId) } : s)),
    );
  }

  async function saveWorkflow(e: React.FormEvent) {
    e.preventDefault();
    setDesignerError(null);
    const missingPipeline = draftSteps.find((s) => s.action === "run_pipeline" && !s.params.pipeline);
    if (missingPipeline) {
      setDesignerError(`El bloque "${missingPipeline.label}" necesita que elijas qué pipeline lanzar.`);
      return;
    }
    try {
      if (editingWorkflowId) {
        await updateWorkflow(editingWorkflowId, workflowName, draftSteps);
      } else {
        await createWorkflow(workflowName, draftSteps);
      }
      setDraftSteps([]);
      setWorkflowName("");
      setEditingWorkflowId(null);
      setSelectedStepId(null);
      setActiveTab("saved");
      await reloadWorkflows();
    } catch (err) {
      setDesignerError(err instanceof ApiError ? err.message : "No se pudo guardar el flujo.");
    }
  }

  function editWorkflow(wf: Workflow) {
    setDesignerError(null);
    setEditingWorkflowId(wf.id);
    setWorkflowName(wf.name);
    setDraftSteps(wf.steps);
    setSelectedStepId(null);
    setActiveTab("editor");
  }

  function cancelEdit() {
    setEditingWorkflowId(null);
    setWorkflowName("");
    setDraftSteps([]);
    setSelectedStepId(null);
    setActiveTab("saved");
  }

  function discardDraft() {
    setDraftSteps([]);
    setSelectedStepId(null);
  }

  async function launchWorkflow(id: string) {
    setLaunchError(null);
    try {
      await runWorkflow(id, notifyByWorkflow[id] ?? false);
    } catch (err) {
      setLaunchError(err instanceof ApiError ? err.message : "No se pudo lanzar el flujo.");
    }
  }

  async function handleRetry(run: WorkflowRun) {
    setLaunchError(null);
    try {
      await retryWorkflowRun(run.id);
      await refetchRuns();
    } catch (err) {
      setLaunchError(err instanceof ApiError ? err.message : "No se pudo reintentar el flujo.");
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
        Añade bloques y arrastra desde el borde derecho de un bloque hasta el izquierdo de otro para marcar una
        dependencia. Haz clic en un bloque para editarlo, o en una conexión para quitarla. Un bloque sin dependencias
        se lanza en paralelo con los demás; uno con dependencias espera a que todas terminen antes de decidir si se
        lanza.
      </p>

      {isAdmin && (
        <div className={styles.tabBar}>
          <button
            type="button"
            className={activeTab === "saved" ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab("saved")}
          >
            Flujos guardados
          </button>
          <button
            type="button"
            className={activeTab === "editor" ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab("editor")}
          >
            Editor
          </button>
        </div>
      )}

      {isAdmin && activeTab === "editor" && (
        <>
          <h2>{editingWorkflowId ? "Editar flujo guardado" : "Diseñar un flujo nuevo"}</h2>
          {designerError && <div className={formStyles.errorBanner}>{designerError}</div>}

          <div className={formStyles.card} style={{ marginBottom: 12 }}>
            <div className={formStyles.field}>
              <label htmlFor="new_step_action">Tipo de bloque a añadir</label>
              <select
                id="new_step_action"
                value={newStepAction}
                onChange={(e) => {
                  const action = e.target.value;
                  setNewStepAction(action);
                  setNewStepPipeline(action === "run_pipeline" ? (pipelines[0] ?? "") : "");
                }}
              >
                {Object.entries(ACTION_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            {newStepAction === "run_pipeline" && (
              <div className={formStyles.field}>
                <label htmlFor="new_step_pipeline">Pipeline</label>
                <select
                  id="new_step_pipeline"
                  value={newStepPipeline}
                  onChange={(e) => setNewStepPipeline(e.target.value)}
                >
                  <option value="">Selecciona un pipeline…</option>
                  {pipelines.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
                {pipelines.length === 0 && (
                  <p className={formStyles.hint}>
                    No hay pipelines configurados en <code>config.json</code>.
                  </p>
                )}
              </div>
            )}
            <button
              type="button"
              className={formStyles.submit}
              onClick={addStep}
              disabled={newStepAction === "run_pipeline" && !newStepPipeline}
            >
              Añadir bloque al flujo
            </button>
          </div>

          {draftSteps.length > 0 && (
            <>
              <WorkflowDiagram
                steps={draftSteps}
                actionLabels={ACTION_LABELS}
                selectedStepId={selectedStepId}
                onSelectStep={setSelectedStepId}
                onConnectSteps={connectSteps}
                onRemoveDependency={removeDependency}
                testId="designer-diagram"
              />

              {selectedStep && (
                <div className={formStyles.card}>
                  <div className={formStyles.field}>
                    <label htmlFor="edit_step_label">Etiqueta del bloque seleccionado</label>
                    <input
                      id="edit_step_label"
                      type="text"
                      value={selectedStep.label}
                      onChange={(e) => updateStep(selectedStep.id, { label: e.target.value })}
                    />
                  </div>
                  <div className={formStyles.field}>
                    <label htmlFor="edit_step_action">Acción del bloque seleccionado</label>
                    <select
                      id="edit_step_action"
                      value={selectedStep.action}
                      onChange={(e) => updateStep(selectedStep.id, { action: e.target.value, params: {} })}
                    >
                      {Object.entries(ACTION_LABELS).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>
                  {selectedStep.action === "run_pipeline" && (
                    <div className={formStyles.field}>
                      <label htmlFor="edit_step_pipeline">Pipeline</label>
                      <select
                        id="edit_step_pipeline"
                        value={(selectedStep.params.pipeline as string) ?? ""}
                        onChange={(e) => updateStep(selectedStep.id, { params: { pipeline: e.target.value } })}
                      >
                        <option value="">Selecciona un pipeline…</option>
                        {pipelines.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                      {pipelines.length === 0 && (
                        <p className={formStyles.hint}>
                          No hay pipelines configurados en <code>config.json</code>.
                        </p>
                      )}
                    </div>
                  )}
                  {selectedStep.depends_on.length > 0 && (
                    <div className={formStyles.field}>
                      <label htmlFor="edit_step_trigger_rule">¿Cuándo lanzar este bloque?</label>
                      <select
                        id="edit_step_trigger_rule"
                        value={selectedStep.trigger_rule}
                        onChange={(e) =>
                          updateStep(selectedStep.id, { trigger_rule: e.target.value as "all_success" | "always" })
                        }
                      >
                        <option value="all_success">Solo si todas sus dependencias tuvieron éxito</option>
                        <option value="always">Aunque alguna dependencia haya fallado</option>
                      </select>
                    </div>
                  )}
                  <button type="button" className={styles.btnDanger} onClick={() => removeStep(selectedStep.id)}>
                    Quitar bloque
                  </button>
                </div>
              )}

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
                  {editingWorkflowId ? "Guardar cambios" : "Guardar flujo"}
                </button>
                <button
                  type="button"
                  className={styles.btn}
                  style={{ marginLeft: 8 }}
                  onClick={() => (editingWorkflowId ? cancelEdit() : discardDraft())}
                >
                  {editingWorkflowId ? "Cancelar edición" : "Descartar borrador"}
                </button>
              </form>
            </>
          )}
        </>
      )}

      {(!isAdmin || activeTab === "saved") && (
        <>
          {!isAdmin && <p>Diseñar o borrar flujos requiere el rol App.Admin. Puedes consultarlos y lanzarlos abajo.</p>}

            <h2>Flujos guardados</h2>
        {launchError && <div className={formStyles.errorBanner}>{launchError}</div>}
        {workflows.length === 0 ? (
          <p>Todavía no hay flujos guardados.</p>
        ) : (
          workflows.map((wf) => (
            <div className={styles.workflowCard} key={wf.id} data-testid="workflow-card">
              <div className={styles.workflowHead}>
                <strong>{wf.name}</strong>
                <span className={styles.stepMeta}>{wf.steps.length} bloque(s)</span>
                {canOperate && (
                  <>
                    <NotifyCheckbox
                      checked={notifyByWorkflow[wf.id] ?? false}
                      onChange={(checked) => setNotifyByWorkflow((prev) => ({ ...prev, [wf.id]: checked }))}
                    />
                    <button type="button" className={styles.btnPrimary} onClick={() => void launchWorkflow(wf.id)}>
                      Lanzar flujo
                    </button>
                  </>
                )}
                {isAdmin && (
                  <button type="button" className={styles.btn} onClick={() => editWorkflow(wf)}>
                    Editar flujo
                  </button>
                )}
                {isAdmin && (
                  <button type="button" className={styles.btnDanger} onClick={() => setPendingDeleteWorkflow(wf)}>
                    Borrar flujo
                  </button>
                )}
              </div>
              <WorkflowDiagram steps={wf.steps} actionLabels={ACTION_LABELS} readOnly height={200} />
              {isAdmin && (
                <div className={styles.readerAccess}>
                  <label htmlFor={`reader-access-${wf.id}`}>
                    Acceso de lectores (App.Reader) — solo estos usuarios pueden lanzar y seguir este flujo desde su
                    Inicio
                  </label>
                  <TagMultiSelect
                    id={`reader-access-${wf.id}`}
                    options={readerUsernames}
                    selected={wf.reader_allowed_users}
                    onChange={(usernames) => void handleSetReaderAccess(wf.id, usernames)}
                    placeholder="+ Dar acceso a un lector…"
                    emptyHint="Ningún lector tiene acceso"
                  />
                </div>
              )}
            </div>
          ))
        )}
  
        <h2>Flujos en curso / recientes</h2>
        {runs.length === 0 ? (
          <p>No hay ejecuciones de flujos en esta sesión del servidor.</p>
        ) : (
          runs.map((run) => {
            const owns = user?.role === ROLE_ADMIN || run.triggered_by === user?.username;
            const canStop = run.status === "running" && owns;
            const canRetry = run.status === "error" && owns && canOperate;
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
                  {run.status === "error" && canRetry && (
                    <button type="button" className={styles.btn} onClick={() => void handleRetry(run)}>
                      Reintentar pasos fallidos
                    </button>
                  )}
                </div>
                <WorkflowDiagram
                  steps={run.steps}
                  actionLabels={ACTION_LABELS}
                  stepStatuses={Object.fromEntries(run.steps.map((s) => [s.id, s.status]))}
                  readOnly
                  height={200}
                />
              </div>
            );
          })
        )}
        </>
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
