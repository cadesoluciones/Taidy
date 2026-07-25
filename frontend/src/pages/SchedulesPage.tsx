import { useEffect, useState } from "react";
import { CirclePause, CirclePlay } from "lucide-react";

import { ROLE_ADMIN } from "../api/auth";
import { ApiError } from "../api/client";
import { fetchPipelines } from "../api/meta";
import { createSchedule, deleteSchedule, fetchSchedules, setScheduleEnabled, type Schedule } from "../api/schedules";
import { fetchWorkflows, type Workflow } from "../api/workflows";
import { useAuth } from "../auth/AuthContext";
import { ConfirmDialog } from "../components/ConfirmDialog";
import formStyles from "../components/Form.module.css";
import { NotifyCheckbox } from "../components/NotifyCheckbox";
import styles from "./SchedulesPage.module.css";

const ACTION_LABELS: Record<string, string> = {
  extract_bc: "BC · Extraer",
  upload_bc: "BC · Subir",
  sync_bc: "BC · Sync (extraer + subir)",
  extract_factorial: "Factorial · Extraer",
  upload_factorial: "Factorial · Subir",
  sync_factorial: "Factorial · Sync (extraer + subir)",
  run_pipeline: "Fabric · Ejecutar pipeline",
  run_workflow: "Flujo (varios bloques)",
};

const NEEDS_MODE_PARALLEL = new Set(["extract_bc", "sync_bc", "extract_factorial", "sync_factorial"]);
const NEEDS_START_ON = new Set(["extract_factorial", "sync_factorial"]);
const NEEDS_SKIP_EXISTING = new Set(["upload_bc", "upload_factorial", "sync_bc", "sync_factorial"]);

function describeFrequency(s: Schedule): string {
  if (s.trigger === "cron") {
    return String(s.trigger_args["expr"] ?? "");
  }
  const hours = Number(s.trigger_args["hours"] ?? 0);
  const minutes = Number(s.trigger_args["minutes"] ?? 0);
  return `cada ${hours}h ${minutes}min`;
}

export function SchedulesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === ROLE_ADMIN;

  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [pendingDelete, setPendingDelete] = useState<Schedule | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const [name, setName] = useState("");
  const [action, setAction] = useState("extract_bc");
  const [triggerKind, setTriggerKind] = useState<"interval" | "cron">("interval");
  const [hours, setHours] = useState(24);
  const [minutes, setMinutes] = useState(0);
  const [cronExpr, setCronExpr] = useState("0 6 * * *");
  const [notify, setNotify] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  // Action-specific parameters -- only the ones relevant to the chosen
  // `action` get sent (mirrors webapp/app.py:page_schedules' conditional
  // widgets exactly, so a scheduled Factorial extract/sync always has the
  // `start_on` it requires, and a scheduled pipeline always has `pipeline`).
  const [mode, setMode] = useState<"incremental" | "full">("incremental");
  const [parallel, setParallel] = useState(1);
  const [startOn, setStartOn] = useState("2025-01-01");
  const [employeeStatus, setEmployeeStatus] = useState<"active" | "inactive" | "all">("active");
  const [skipExisting, setSkipExisting] = useState(false);
  const [pipelines, setPipelines] = useState<string[]>([]);
  const [pipeline, setPipeline] = useState("");
  const [pollSeconds, setPollSeconds] = useState(15);
  const [workflowsList, setWorkflowsList] = useState<Workflow[]>([]);
  const [workflowId, setWorkflowId] = useState("");

  async function reload() {
    setSchedules((await fetchSchedules()).items);
  }

  useEffect(() => {
    void reload();
  }, []);

  useEffect(() => {
    if (action === "run_pipeline") {
      fetchPipelines().then((res) => {
        setPipelines(res.items);
        setPipeline((prev) => prev || res.items[0] || "");
      });
    }
    if (action === "run_workflow") {
      fetchWorkflows().then((res) => {
        setWorkflowsList(res.items);
        setWorkflowId((prev) => prev || res.items[0]?.id || "");
      });
    }
  }, [action]);

  /** Returns null (with the caller responsible for showing an error) when a
   * required selection -- a pipeline, a saved workflow -- hasn't been made. */
  function buildParams(): Record<string, unknown> | null {
    const params: Record<string, unknown> = { notify };

    if (action === "run_workflow") {
      if (!workflowId) return null;
      params.workflow_id = workflowId;
      return params;
    }

    if (NEEDS_MODE_PARALLEL.has(action)) {
      params.mode = mode;
      params.parallel = parallel;
    }
    if (NEEDS_START_ON.has(action)) {
      params.start_on = startOn;
      params.employee_status = employeeStatus;
    }
    if (NEEDS_SKIP_EXISTING.has(action)) {
      params.skip_existing = skipExisting;
    }
    if (action === "run_pipeline") {
      if (!pipeline) return null;
      params.pipeline = pipeline;
      params.wait = true;
      params.poll_seconds = pollSeconds;
    }
    return params;
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreateSuccess(null);
    if (!name.trim()) {
      setCreateError("Indica un nombre para la tarea.");
      return;
    }
    if (triggerKind === "interval" && hours <= 0 && minutes <= 0) {
      setCreateError("El intervalo debe ser mayor que 0.");
      return;
    }
    const params = buildParams();
    if (params === null) {
      setCreateError(action === "run_workflow" ? "Elige un flujo guardado." : "Elige un pipeline configurado.");
      return;
    }
    try {
      await createSchedule({
        name: name.trim(),
        action,
        params,
        trigger: triggerKind,
        trigger_args: triggerKind === "interval" ? { hours, minutes } : { expr: cronExpr.trim() },
      });
      setCreateSuccess(`Tarea '${name}' creada.`);
      setName("");
      setNotify(false);
      await reload();
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "No se pudo crear la tarea.");
    }
  }

  async function toggleEnabled(s: Schedule) {
    await setScheduleEnabled(s.id, !s.enabled);
    await reload();
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setIsBusy(true);
    try {
      await deleteSchedule(pendingDelete.id);
      await reload();
    } finally {
      setIsBusy(false);
      setPendingDelete(null);
    }
  }

  return (
    <section>
      <h1>Tareas programadas</h1>
      <p>
        Se ejecutan en segundo plano mientras el servidor de la API siga vivo. En producción, arráncalo bajo un
        supervisor de procesos (systemd, Docker con restart policy, etc.).
      </p>

      {isAdmin && (
        <>
          <h2>Nueva tarea</h2>
          {createSuccess && <div className={formStyles.successBanner}>{createSuccess}</div>}
          {createError && <div className={formStyles.errorBanner}>{createError}</div>}
          <form className={formStyles.card} onSubmit={handleCreate}>
            <div className={formStyles.field}>
              <label htmlFor="name">Nombre de la tarea</label>
              <input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className={formStyles.field}>
              <label htmlFor="action">Acción a programar</label>
              <select id="action" value={action} onChange={(e) => setAction(e.target.value)}>
                {Object.entries(ACTION_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            {action === "run_workflow" &&
              (workflowsList.length === 0 ? (
                <p className={formStyles.hint}>Todavía no hay flujos guardados en "Flujos".</p>
              ) : (
                <div className={formStyles.field}>
                  <label htmlFor="sched_workflow">Flujo</label>
                  <select id="sched_workflow" value={workflowId} onChange={(e) => setWorkflowId(e.target.value)}>
                    {workflowsList.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                </div>
              ))}

            {NEEDS_MODE_PARALLEL.has(action) && (
              <div className={formStyles.grid}>
                <div className={formStyles.field}>
                  <label htmlFor="sched_mode">Modo</label>
                  <select id="sched_mode" value={mode} onChange={(e) => setMode(e.target.value as "incremental" | "full")}>
                    <option value="incremental">incremental</option>
                    <option value="full">full</option>
                  </select>
                </div>
                <div className={formStyles.field}>
                  <label htmlFor="sched_parallel">Hilos en paralelo</label>
                  <input
                    id="sched_parallel"
                    type="number"
                    min={1}
                    value={parallel}
                    onChange={(e) => setParallel(Number(e.target.value))}
                  />
                </div>
              </div>
            )}

            {NEEDS_START_ON.has(action) && (
              <>
                <div className={formStyles.grid}>
                  <div className={formStyles.field}>
                    <label htmlFor="sched_start_on">Fecha de inicio (solo se usa si aún no hay checkpoint)</label>
                    <input
                      id="sched_start_on"
                      type="date"
                      value={startOn}
                      onChange={(e) => setStartOn(e.target.value)}
                    />
                  </div>
                  <div className={formStyles.field}>
                    <label htmlFor="sched_emp_status">Empleados</label>
                    <select
                      id="sched_emp_status"
                      value={employeeStatus}
                      onChange={(e) => setEmployeeStatus(e.target.value as "active" | "inactive" | "all")}
                    >
                      <option value="active">active</option>
                      <option value="inactive">inactive</option>
                      <option value="all">all</option>
                    </select>
                  </div>
                </div>
                <p className={formStyles.hint}>
                  "Hasta" se calcula automáticamente como la fecha de hoy en cada ejecución.
                </p>
              </>
            )}

            {NEEDS_SKIP_EXISTING.has(action) && (
              <label className={formStyles.checkboxField}>
                <input type="checkbox" checked={skipExisting} onChange={(e) => setSkipExisting(e.target.checked)} />
                <span>Omitir ficheros ya subidos</span>
              </label>
            )}

            {action === "run_pipeline" &&
              (pipelines.length === 0 ? (
                <p className={formStyles.hint}>No hay pipelines configurados en config.json todavía.</p>
              ) : (
                <div className={formStyles.grid}>
                  <div className={formStyles.field}>
                    <label htmlFor="sched_pipeline">Pipeline</label>
                    <select id="sched_pipeline" value={pipeline} onChange={(e) => setPipeline(e.target.value)}>
                      {pipelines.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className={formStyles.field}>
                    <label htmlFor="sched_poll">Cada cuántos segundos consultar el estado</label>
                    <input
                      id="sched_poll"
                      type="number"
                      min={5}
                      step={5}
                      value={pollSeconds}
                      onChange={(e) => setPollSeconds(Number(e.target.value))}
                    />
                  </div>
                </div>
              ))}

            <div className={formStyles.field}>
              <label htmlFor="trigger_kind">Frecuencia</label>
              <select id="trigger_kind" value={triggerKind} onChange={(e) => setTriggerKind(e.target.value as "interval" | "cron")}>
                <option value="interval">Intervalo</option>
                <option value="cron">Cron</option>
              </select>
            </div>
            {triggerKind === "interval" ? (
              <div className={formStyles.grid}>
                <div className={formStyles.field}>
                  <label htmlFor="hours">Cada cuántas horas</label>
                  <input id="hours" type="number" min={0} value={hours} onChange={(e) => setHours(Number(e.target.value))} />
                </div>
                <div className={formStyles.field}>
                  <label htmlFor="minutes">Y cuántos minutos</label>
                  <input
                    id="minutes"
                    type="number"
                    min={0}
                    value={minutes}
                    onChange={(e) => setMinutes(Number(e.target.value))}
                  />
                </div>
              </div>
            ) : (
              <div className={formStyles.field}>
                <label htmlFor="cron_expr">Expresión cron (minuto hora día mes día-semana)</label>
                <input id="cron_expr" type="text" value={cronExpr} onChange={(e) => setCronExpr(e.target.value)} />
              </div>
            )}
            <NotifyCheckbox checked={notify} onChange={setNotify} />
            <button type="submit" className={formStyles.submit}>
              Crear tarea programada
            </button>
          </form>
        </>
      )}

      <h2>Tareas existentes</h2>
      {schedules.length === 0 ? (
        <p>No hay tareas programadas todavía.</p>
      ) : (
        schedules.map((s) => (
          <div className={styles.row} key={s.id}>
            <strong className={styles.name}>{s.name}</strong>
            <span>{ACTION_LABELS[s.action] ?? s.action}</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              {s.enabled ? (
                <CirclePlay size={14} color="var(--color-success)" />
              ) : (
                <CirclePause size={14} color="var(--color-text-muted)" />
              )}
              {s.enabled ? "Activa" : "Pausada"}
            </span>
            <span className={styles.freq}>{describeFrequency(s)}</span>
            {isAdmin && (
              <div className={styles.actions}>
                <button type="button" className={styles.btn} onClick={() => void toggleEnabled(s)}>
                  {s.enabled ? "Pausar" : "Reanudar"}
                </button>
                <button type="button" className={styles.btnDanger} onClick={() => setPendingDelete(s)}>
                  Borrar
                </button>
              </div>
            )}
          </div>
        ))
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Borrar tarea programada"
        description={`Vas a borrar la tarea programada "${pendingDelete?.name}". Dejará de ejecutarse y no se puede deshacer.`}
        confirmLabel="Borrar definitivamente"
        busy={isBusy}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </section>
  );
}
