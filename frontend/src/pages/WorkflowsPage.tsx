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
  reorderWorkflows,
  retryWorkflowRun,
  runWorkflow,
  setWorkflowReaderAccess,
  stopWorkflowRun,
  updateWorkflow,
  type StepDefinition,
  type Workflow,
  type WorkflowRun,
} from "../api/workflows";
import type { SyncApplyDirection } from "../api/tasks";
import { useAuth } from "../auth/AuthContext";
import { ACTION_LABELS } from "../components/actionLabels";
import { ConfirmDialog } from "../components/ConfirmDialog";
import formStyles from "../components/Form.module.css";
import { NotifyCheckbox } from "../components/NotifyCheckbox";
import { StatusBadge } from "../components/StatusBadge";
import { SyncApplyFields } from "../components/SyncApplyFields";
import { TagMultiSelect } from "../components/TagMultiSelect";
import { WorkflowDiagram } from "../components/WorkflowDiagram";
import { usePolling } from "../hooks/usePolling";
import { useDragReorder } from "../hooks/useDragReorder";
import { NEEDS_MODE_PARALLEL, NEEDS_START_ON, NEEDS_SKIP_EXISTING } from "../utils/actionParamGroups";
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
  const [workflowDescription, setWorkflowDescription] = useState("");
  const [designerError, setDesignerError] = useState<string | null>(null);
  const [editingWorkflowId, setEditingWorkflowId] = useState<string | null>(null);

  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const [pendingDeleteWorkflow, setPendingDeleteWorkflow] = useState<Workflow | null>(null);
  const [pendingStopRun, setPendingStopRun] = useState<WorkflowRun | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [notifyByWorkflow, setNotifyByWorkflow] = useState<Record<string, boolean>>({});
  const [readerUsernames, setReaderUsernames] = useState<string[]>([]);
  const [pipelines, setPipelines] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"saved" | "runs" | "editor">("saved");
  const [newStepAction, setNewStepAction] = useState<string>("extract_bc");
  const [newStepPipeline, setNewStepPipeline] = useState<string>("");
  const [newStepSyncMapping, setNewStepSyncMapping] = useState("");
  const [newStepSyncDirection, setNewStepSyncDirection] = useState<SyncApplyDirection>("to_target");
  const [newStepSyncConfirmLargeBatch, setNewStepSyncConfirmLargeBatch] = useState(false);
  const [newStepWorkflowId, setNewStepWorkflowId] = useState("");
  const [newStepMode, setNewStepMode] = useState<"incremental" | "full">("incremental");
  const [newStepParallel, setNewStepParallel] = useState(1);
  const [newStepStartOn, setNewStepStartOn] = useState("2025-01-01");
  const [newStepEmployeeStatus, setNewStepEmployeeStatus] = useState<"active" | "inactive" | "all">("active");
  const [newStepSkipExisting, setNewStepSkipExisting] = useState(false);
  const [stepPositions, setStepPositions] = useState<Record<string, { x: number; y: number }>>({});

  const { data: runsData, refetch: refetchRuns } = usePolling(() => fetchWorkflowRuns(), 3000);
  const runs = runsData?.items ?? [];
  const selectedStep = draftSteps.find((s) => s.id === selectedStepId) ?? null;
  const selectedWorkflow = workflows.find((w) => w.id === selectedWorkflowId) ?? null;

  async function reloadWorkflows() {
    setWorkflows((await fetchWorkflows()).items);
  }

  useEffect(() => {
    void reloadWorkflows();
  }, []);

  // Keep a workflow selected in "Flujos guardados" whenever possible --
  // defaults to the first one on load, follows deletions (falls back once
  // the selected id disappears), and otherwise leaves the user's choice alone.
  useEffect(() => {
    setSelectedWorkflowId((prev) => {
      if (prev && workflows.some((w) => w.id === prev)) return prev;
      return workflows[0]?.id ?? null;
    });
  }, [workflows]);

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

  // A block can't launch the workflow it's currently being edited into --
  // that would be an immediate self-reference loop.
  const workflowChoicesForStep = workflows.filter((w) => w.id !== editingWorkflowId);

  useEffect(() => {
    if (newStepAction === "run_workflow" && !newStepWorkflowId && workflowChoicesForStep.length > 0) {
      setNewStepWorkflowId(workflowChoicesForStep[0]?.id ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newStepAction, workflowChoicesForStep.length]);

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

  async function handleReorderWorkflows(orderedIds: string[]) {
    const byId = new Map(workflows.map((w) => [w.id, w]));
    // Optimistic reorder -- the drag gesture should feel instant, not wait
    // on a round trip; reloadWorkflows() below reconciles with the server.
    setWorkflows(orderedIds.map((id) => byId.get(id)).filter((w): w is Workflow => w !== undefined));
    try {
      await reorderWorkflows(orderedIds);
    } catch {
      await reloadWorkflows();
    }
  }

  const { handlersFor: workflowDragHandlers } = useDragReorder(workflows, (w) => w.id, (ids) => void handleReorderWorkflows(ids));

  /** Builds `params` for the block about to be added, mirroring
   * SchedulesPage's buildParams() -- returns null when a required
   * selection (pipeline, mapping, flujo) hasn't been made yet. */
  function buildNewStepParams(): Record<string, unknown> | null {
    if (newStepAction === "run_pipeline") {
      if (!newStepPipeline) return null;
      return { pipeline: newStepPipeline };
    }
    if (newStepAction === "sync_apply") {
      if (!newStepSyncMapping) return null;
      return {
        mapping: newStepSyncMapping,
        direction: newStepSyncDirection,
        confirm_large_batch: newStepSyncConfirmLargeBatch,
      };
    }
    if (newStepAction === "run_workflow") {
      if (!newStepWorkflowId) return null;
      return { workflow_id: newStepWorkflowId };
    }
    const params: Record<string, unknown> = {};
    if (NEEDS_MODE_PARALLEL.has(newStepAction)) {
      params.mode = newStepMode;
      params.parallel = newStepParallel;
    }
    if (NEEDS_START_ON.has(newStepAction)) {
      params.start_on = newStepStartOn;
      params.employee_status = newStepEmployeeStatus;
    }
    if (NEEDS_SKIP_EXISTING.has(newStepAction)) {
      params.skip_existing = newStepSkipExisting;
    }
    return params;
  }

  function addStep() {
    const params = buildNewStepParams();
    if (params === null) return;
    setDesignerError(null);
    const id = `step_${Math.random().toString(36).slice(2, 10)}`;
    const label = `Bloque ${draftSteps.length + 1}`;
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
    setStepPositions((prev) => {
      if (!(id in prev)) return prev;
      const { [id]: _removed, ...rest } = prev;
      return rest;
    });
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

  async function saveWorkflow() {
    setDesignerError(null);
    if (!workflowName.trim()) {
      setDesignerError("El flujo necesita un nombre.");
      return;
    }
    const missingPipeline = draftSteps.find((s) => s.action === "run_pipeline" && !s.params.pipeline);
    if (missingPipeline) {
      setDesignerError(`El bloque "${missingPipeline.label}" necesita que elijas qué pipeline lanzar.`);
      return;
    }
    const missingMapping = draftSteps.find((s) => s.action === "sync_apply" && !s.params.mapping);
    if (missingMapping) {
      setDesignerError(`El bloque "${missingMapping.label}" necesita que elijas qué mapeo sincronizar.`);
      return;
    }
    const missingWorkflow = draftSteps.find((s) => s.action === "run_workflow" && !s.params.workflow_id);
    if (missingWorkflow) {
      setDesignerError(`El bloque "${missingWorkflow.label}" necesita que elijas qué flujo lanzar.`);
      return;
    }
    try {
      const saved = editingWorkflowId
        ? await updateWorkflow(editingWorkflowId, workflowName, draftSteps, workflowDescription)
        : await createWorkflow(workflowName, draftSteps, workflowDescription);
      setDraftSteps([]);
      setWorkflowName("");
      setWorkflowDescription("");
      setEditingWorkflowId(null);
      setSelectedStepId(null);
      setStepPositions({});
      setSelectedWorkflowId(saved.id);
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
    setWorkflowDescription(wf.description);
    setDraftSteps(wf.steps);
    setSelectedStepId(null);
    setStepPositions({});
    setActiveTab("editor");
  }

  /** Loads an existing workflow's steps into the draft as a NEW workflow
   * (editingWorkflowId stays null, so saving creates rather than updates) --
   * lets a similar flow be built by tweaking a copy instead of re-adding
   * every block by hand. Mirrors SyncMappingManager's duplicateMapping(). */
  function duplicateWorkflow(wf: Workflow) {
    setDesignerError(null);
    setEditingWorkflowId(null);
    setWorkflowName(`${wf.name} (copia)`);
    setWorkflowDescription(wf.description);
    setDraftSteps(wf.steps);
    setSelectedStepId(null);
    setStepPositions({});
    setActiveTab("editor");
  }

  function cancelEdit() {
    setEditingWorkflowId(null);
    setWorkflowName("");
    setWorkflowDescription("");
    setDraftSteps([]);
    setSelectedStepId(null);
    setStepPositions({});
    setActiveTab("saved");
  }

  function discardDraft() {
    setDraftSteps([]);
    setSelectedStepId(null);
    setStepPositions({});
    setWorkflowName("");
    setWorkflowDescription("");
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
          className={activeTab === "runs" ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab("runs")}
        >
          Flujos en curso / recientes
        </button>
        {isAdmin && (
          <button
            type="button"
            className={activeTab === "editor" ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab("editor")}
          >
            Editor
          </button>
        )}
      </div>

      {isAdmin && activeTab === "editor" && (
        <>
          <h2>{editingWorkflowId ? "Editar flujo guardado" : "Diseñar un flujo nuevo"}</h2>
          {designerError && <div className={formStyles.errorBanner}>{designerError}</div>}

          <div className={styles.designerLayout}>
            <div className={styles.designerOptions}>
              <div className={formStyles.card}>
                <div className={formStyles.field}>
                  <label htmlFor="workflow_name">Nombre del flujo</label>
                  <input
                    id="workflow_name"
                    type="text"
                    value={workflowName}
                    onChange={(e) => setWorkflowName(e.target.value)}
                  />
                </div>
                <div className={formStyles.field}>
                  <label htmlFor="workflow_description">Descripción (opcional)</label>
                  <input
                    id="workflow_description"
                    type="text"
                    value={workflowDescription}
                    onChange={(e) => setWorkflowDescription(e.target.value)}
                  />
                </div>
              </div>

              <div className={formStyles.card}>
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
                {newStepAction === "sync_apply" && (
                  <SyncApplyFields
                    idPrefix="new_step_sync"
                    mapping={newStepSyncMapping}
                    onMappingChange={setNewStepSyncMapping}
                    direction={newStepSyncDirection}
                    onDirectionChange={setNewStepSyncDirection}
                    confirmLargeBatch={newStepSyncConfirmLargeBatch}
                    onConfirmLargeBatchChange={setNewStepSyncConfirmLargeBatch}
                  />
                )}
                {newStepAction === "run_workflow" &&
                  (workflowChoicesForStep.length === 0 ? (
                    <p className={formStyles.hint}>No hay otro flujo guardado que se pueda lanzar desde aquí.</p>
                  ) : (
                    <div className={formStyles.field}>
                      <label htmlFor="new_step_workflow">Flujo</label>
                      <select
                        id="new_step_workflow"
                        value={newStepWorkflowId}
                        onChange={(e) => setNewStepWorkflowId(e.target.value)}
                      >
                        {workflowChoicesForStep.map((w) => (
                          <option key={w.id} value={w.id}>
                            {w.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                {NEEDS_MODE_PARALLEL.has(newStepAction) && (
                  <div className={formStyles.grid}>
                    <div className={formStyles.field}>
                      <label htmlFor="new_step_mode">Modo</label>
                      <select
                        id="new_step_mode"
                        value={newStepMode}
                        onChange={(e) => setNewStepMode(e.target.value as "incremental" | "full")}
                      >
                        <option value="incremental">incremental</option>
                        <option value="full">full</option>
                      </select>
                    </div>
                    <div className={formStyles.field}>
                      <label htmlFor="new_step_parallel">Hilos en paralelo</label>
                      <input
                        id="new_step_parallel"
                        type="number"
                        min={1}
                        value={newStepParallel}
                        onChange={(e) => setNewStepParallel(Number(e.target.value))}
                      />
                    </div>
                  </div>
                )}
                {NEEDS_START_ON.has(newStepAction) && (
                  <div className={formStyles.grid}>
                    <div className={formStyles.field}>
                      <label htmlFor="new_step_start_on">Fecha de inicio (solo si aún no hay checkpoint)</label>
                      <input
                        id="new_step_start_on"
                        type="date"
                        value={newStepStartOn}
                        onChange={(e) => setNewStepStartOn(e.target.value)}
                      />
                    </div>
                    <div className={formStyles.field}>
                      <label htmlFor="new_step_emp_status">Empleados</label>
                      <select
                        id="new_step_emp_status"
                        value={newStepEmployeeStatus}
                        onChange={(e) => setNewStepEmployeeStatus(e.target.value as "active" | "inactive" | "all")}
                      >
                        <option value="active">active</option>
                        <option value="inactive">inactive</option>
                        <option value="all">all</option>
                      </select>
                    </div>
                  </div>
                )}
                {NEEDS_SKIP_EXISTING.has(newStepAction) && (
                  <label className={formStyles.checkboxField}>
                    <input
                      type="checkbox"
                      checked={newStepSkipExisting}
                      onChange={(e) => setNewStepSkipExisting(e.target.checked)}
                    />
                    <span>Omitir ficheros ya subidos</span>
                  </label>
                )}
                <button
                  type="button"
                  className={formStyles.submit}
                  onClick={addStep}
                  disabled={buildNewStepParams() === null}
                >
                  Añadir bloque al flujo
                </button>
              </div>

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
                  {selectedStep.action === "sync_apply" && (
                    <SyncApplyFields
                      idPrefix="edit_step_sync"
                      mapping={(selectedStep.params.mapping as string) ?? ""}
                      onMappingChange={(mapping) =>
                        updateStep(selectedStep.id, { params: { ...selectedStep.params, mapping } })
                      }
                      direction={(selectedStep.params.direction as SyncApplyDirection) ?? "to_target"}
                      onDirectionChange={(direction) =>
                        updateStep(selectedStep.id, { params: { ...selectedStep.params, direction } })
                      }
                      confirmLargeBatch={Boolean(selectedStep.params.confirm_large_batch)}
                      onConfirmLargeBatchChange={(confirm_large_batch) =>
                        updateStep(selectedStep.id, { params: { ...selectedStep.params, confirm_large_batch } })
                      }
                    />
                  )}
                  {selectedStep.action === "run_workflow" &&
                    (workflowChoicesForStep.length === 0 ? (
                      <p className={formStyles.hint}>No hay otro flujo guardado que se pueda lanzar desde aquí.</p>
                    ) : (
                      <div className={formStyles.field}>
                        <label htmlFor="edit_step_workflow">Flujo</label>
                        <select
                          id="edit_step_workflow"
                          value={(selectedStep.params.workflow_id as string) ?? ""}
                          onChange={(e) =>
                            updateStep(selectedStep.id, { params: { workflow_id: e.target.value } })
                          }
                        >
                          {workflowChoicesForStep.map((w) => (
                            <option key={w.id} value={w.id}>
                              {w.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    ))}
                  {NEEDS_MODE_PARALLEL.has(selectedStep.action) && (
                    <div className={formStyles.grid}>
                      <div className={formStyles.field}>
                        <label htmlFor="edit_step_mode">Modo</label>
                        <select
                          id="edit_step_mode"
                          value={(selectedStep.params.mode as string) ?? "incremental"}
                          onChange={(e) =>
                            updateStep(selectedStep.id, { params: { ...selectedStep.params, mode: e.target.value } })
                          }
                        >
                          <option value="incremental">incremental</option>
                          <option value="full">full</option>
                        </select>
                      </div>
                      <div className={formStyles.field}>
                        <label htmlFor="edit_step_parallel">Hilos en paralelo</label>
                        <input
                          id="edit_step_parallel"
                          type="number"
                          min={1}
                          value={Number(selectedStep.params.parallel ?? 1)}
                          onChange={(e) =>
                            updateStep(selectedStep.id, {
                              params: { ...selectedStep.params, parallel: Number(e.target.value) },
                            })
                          }
                        />
                      </div>
                    </div>
                  )}
                  {NEEDS_START_ON.has(selectedStep.action) && (
                    <div className={formStyles.grid}>
                      <div className={formStyles.field}>
                        <label htmlFor="edit_step_start_on">Fecha de inicio (solo si aún no hay checkpoint)</label>
                        <input
                          id="edit_step_start_on"
                          type="date"
                          value={(selectedStep.params.start_on as string) ?? "2025-01-01"}
                          onChange={(e) =>
                            updateStep(selectedStep.id, {
                              params: { ...selectedStep.params, start_on: e.target.value },
                            })
                          }
                        />
                      </div>
                      <div className={formStyles.field}>
                        <label htmlFor="edit_step_emp_status">Empleados</label>
                        <select
                          id="edit_step_emp_status"
                          value={(selectedStep.params.employee_status as string) ?? "active"}
                          onChange={(e) =>
                            updateStep(selectedStep.id, {
                              params: { ...selectedStep.params, employee_status: e.target.value },
                            })
                          }
                        >
                          <option value="active">active</option>
                          <option value="inactive">inactive</option>
                          <option value="all">all</option>
                        </select>
                      </div>
                    </div>
                  )}
                  {NEEDS_SKIP_EXISTING.has(selectedStep.action) && (
                    <label className={formStyles.checkboxField}>
                      <input
                        type="checkbox"
                        checked={Boolean(selectedStep.params.skip_existing)}
                        onChange={(e) =>
                          updateStep(selectedStep.id, {
                            params: { ...selectedStep.params, skip_existing: e.target.checked },
                          })
                        }
                      />
                      <span>Omitir ficheros ya subidos</span>
                    </label>
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

              {draftSteps.length > 0 && (
                <div className={formStyles.card}>
                  <button type="button" className={formStyles.submit} onClick={() => void saveWorkflow()}>
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
                </div>
              )}
            </div>

            <div className={styles.designerCanvas}>
              {draftSteps.length > 0 ? (
                <WorkflowDiagram
                  steps={draftSteps}
                  actionLabels={ACTION_LABELS}
                  selectedStepId={selectedStepId}
                  onSelectStep={setSelectedStepId}
                  onConnectSteps={connectSteps}
                  onRemoveDependency={removeDependency}
                  nodePositions={stepPositions}
                  onNodePositionChange={(id, position) => setStepPositions((prev) => ({ ...prev, [id]: position }))}
                  height="100%"
                  testId="designer-diagram"
                />
              ) : (
                <div className={styles.designerEmpty}>
                  <p>Añade un bloque para empezar a diseñar el flujo.</p>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {activeTab === "saved" && (
        <>
          {!isAdmin && <p>Diseñar o borrar flujos requiere el rol App.Admin. Puedes consultarlos y lanzarlos abajo.</p>}

          <h2>Flujos guardados</h2>
        {launchError && <div className={formStyles.errorBanner}>{launchError}</div>}
        {workflows.length === 0 ? (
          <p>Todavía no hay flujos guardados.</p>
        ) : (
          <div className={styles.savedLayout}>
            <div className={styles.savedList}>
              {workflows.map((wf) => (
                <button
                  type="button"
                  key={wf.id}
                  className={wf.id === selectedWorkflowId ? styles.savedListItemActive : styles.savedListItem}
                  onClick={() => setSelectedWorkflowId(wf.id)}
                  {...(isAdmin ? workflowDragHandlers(wf.id) : {})}
                >
                  <strong>{wf.name}</strong>
                  <span className={styles.stepMeta}>{wf.steps.length} bloque(s)</span>
                  <span className={styles.savedListAccess}>
                    {wf.reader_allowed_users.length > 0
                      ? `Acceso: ${wf.reader_allowed_users.join(", ")}`
                      : "Sin lectores con acceso"}
                  </span>
                </button>
              ))}
            </div>

            <div className={styles.savedDetail}>
              {selectedWorkflow && (
                <div className={styles.workflowCard} data-testid="workflow-card">
                  <div className={styles.workflowHead}>
                    <strong>{selectedWorkflow.name}</strong>
                    <span className={styles.stepMeta}>{selectedWorkflow.steps.length} bloque(s)</span>
                    {canOperate && (
                      <>
                        <NotifyCheckbox
                          checked={notifyByWorkflow[selectedWorkflow.id] ?? false}
                          onChange={(checked) =>
                            setNotifyByWorkflow((prev) => ({ ...prev, [selectedWorkflow.id]: checked }))
                          }
                        />
                        <button
                          type="button"
                          className={styles.btnPrimary}
                          onClick={() => void launchWorkflow(selectedWorkflow.id)}
                        >
                          Lanzar flujo
                        </button>
                      </>
                    )}
                    {isAdmin && (
                      <button type="button" className={styles.btn} onClick={() => editWorkflow(selectedWorkflow)}>
                        Editar flujo
                      </button>
                    )}
                    {isAdmin && (
                      <button type="button" className={styles.btn} onClick={() => duplicateWorkflow(selectedWorkflow)}>
                        Duplicar
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        type="button"
                        className={styles.btnDanger}
                        onClick={() => setPendingDeleteWorkflow(selectedWorkflow)}
                      >
                        Borrar flujo
                      </button>
                    )}
                  </div>
                  {selectedWorkflow.description && <p className={styles.stepMeta}>{selectedWorkflow.description}</p>}
                  <WorkflowDiagram
                    steps={selectedWorkflow.steps}
                    actionLabels={ACTION_LABELS}
                    readOnly
                    height={420}
                  />
                  {isAdmin && (
                    <div className={styles.readerAccess}>
                      <label htmlFor={`reader-access-${selectedWorkflow.id}`}>
                        Acceso de lectores (App.Reader) — solo estos usuarios pueden lanzar y seguir este flujo desde
                        su Inicio
                      </label>
                      <TagMultiSelect
                        id={`reader-access-${selectedWorkflow.id}`}
                        options={readerUsernames}
                        selected={selectedWorkflow.reader_allowed_users}
                        onChange={(usernames) => void handleSetReaderAccess(selectedWorkflow.id, usernames)}
                        placeholder="+ Dar acceso a un lector…"
                        emptyHint="Ningún lector tiene acceso"
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
        </>
      )}

      {activeTab === "runs" && (
        <>
          <h2>Flujos en curso / recientes</h2>
          {launchError && <div className={formStyles.errorBanner}>{launchError}</div>}
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
                    stepDetails={Object.fromEntries(run.steps.map((s) => [s.id, s.detail]))}
                    readOnly
                    height={340}
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
