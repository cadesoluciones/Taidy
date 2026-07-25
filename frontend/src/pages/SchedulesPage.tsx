import { useEffect, useState } from "react";
import { CirclePause, CirclePlay } from "lucide-react";

import { ROLE_ADMIN } from "../api/auth";
import { ApiError } from "../api/client";
import { createSchedule, deleteSchedule, fetchSchedules, setScheduleEnabled, type Schedule } from "../api/schedules";
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
};

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

  async function reload() {
    setSchedules((await fetchSchedules()).items);
  }

  useEffect(() => {
    void reload();
  }, []);

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
    try {
      await createSchedule({
        name: name.trim(),
        action,
        params: { notify },
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
