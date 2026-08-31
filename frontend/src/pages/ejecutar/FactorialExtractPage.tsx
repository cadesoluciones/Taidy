import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Settings } from "lucide-react";

import { ROLE_ADMIN, ROLE_READER } from "../../api/auth";
import { ApiError } from "../../api/client";
import { fetchFactorialTables } from "../../api/meta";
import { extractFactorial } from "../../api/tasks";
import { useAuth } from "../../auth/AuthContext";
import formStyles from "../../components/Form.module.css";
import { NotifyCheckbox } from "../../components/NotifyCheckbox";
import { PageHeader } from "../../components/PageHeader";
import { ReadOnlyNotice } from "../../components/ReadOnlyNotice";
import { TagMultiSelect } from "../../components/TagMultiSelect";

function parseEmployeeIds(raw: string): { ids: number[] | null; error: string | null } {
  const trimmed = raw.trim();
  if (!trimmed) return { ids: null, error: null };
  const parts = trimmed.split(",").map((p) => p.trim()).filter(Boolean);
  const ids = parts.map(Number);
  if (ids.some((n) => Number.isNaN(n))) {
    return { ids: null, error: "Los IDs de empleados deben ser números separados por comas (ej. 123, 456)." };
  }
  return { ids, error: null };
}

export function FactorialExtractPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === ROLE_ADMIN;
  const isReader = user?.role === ROLE_READER;

  const [startOn, setStartOn] = useState("2025-01-01");
  const [endOn, setEndOn] = useState(new Date().toISOString().slice(0, 10));
  const [employeeStatus, setEmployeeStatus] = useState<"active" | "inactive" | "all">("active");
  const [employeesRaw, setEmployeesRaw] = useState("");
  const [tables, setTables] = useState<string[]>([]);
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [mode, setMode] = useState<"full" | "incremental">("full");
  const [parallel, setParallel] = useState(5);
  const [outputDir, setOutputDir] = useState("./exports_factorial");
  const [resetAll, setResetAll] = useState(false);
  const [dryRun, setDryRun] = useState(false);
  const [verbose, setVerbose] = useState(false);
  const [notify, setNotify] = useState(false);

  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchFactorialTables()
      .then((res) => setTables(res.items))
      .catch(() => setTables([]));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSuccess(null);
    setError(null);

    if (startOn > endOn) {
      setError("'Desde' no puede ser posterior a 'Hasta'.");
      return;
    }
    const { ids, error: parseError } = parseEmployeeIds(employeesRaw);
    if (parseError) {
      setError(parseError);
      return;
    }
    if (resetAll && !isAdmin) {
      setError("Resetear checkpoints es una operación crítica: requiere el rol App.Admin.");
      return;
    }

    setIsSubmitting(true);
    try {
      const task = await extractFactorial({
        start_on: startOn,
        end_on: endOn,
        employees: ids,
        employee_status: employeeStatus,
        tables: selectedTables.length ? selectedTables : null,
        output_dir: outputDir.trim(),
        mode,
        parallel,
        reset_all_checkpoints: resetAll,
        dry_run: dryRun,
        verbose,
        notify,
      });
      setSuccess(`Tarea iniciada (${task.id.slice(0, 8)}). Sigue el progreso en Tareas en curso.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo iniciar la tarea.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section>
      <PageHeader title="Extraer tablas de Factorial HR" />
      {success && <div className={formStyles.successBanner}>{success}</div>}
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {isReader && <ReadOnlyNotice action="lanzar extracciones" />}
      <form className={formStyles.card} onSubmit={handleSubmit}>
        <div className={formStyles.grid}>
          <div className={formStyles.field}>
            <label htmlFor="start_on">Desde</label>
            <input id="start_on" type="date" value={startOn} onChange={(e) => setStartOn(e.target.value)} />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="end_on">Hasta</label>
            <input id="end_on" type="date" value={endOn} onChange={(e) => setEndOn(e.target.value)} />
          </div>
        </div>
        <div className={formStyles.grid}>
          <div className={formStyles.field}>
            <label htmlFor="employee_status">Empleados</label>
            <select
              id="employee_status"
              value={employeeStatus}
              onChange={(e) => setEmployeeStatus(e.target.value as "active" | "inactive" | "all")}
            >
              <option value="active">active</option>
              <option value="inactive">inactive</option>
              <option value="all">all</option>
            </select>
          </div>
          <div className={formStyles.field}>
            <label htmlFor="employees">IDs de empleados (coma-separados)</label>
            <input id="employees" type="text" value={employeesRaw} onChange={(e) => setEmployeesRaw(e.target.value)} />
          </div>
        </div>
        <div className={formStyles.field}>
          <div className={formStyles.labelRow}>
            <label htmlFor="tables">Tablas (vacío = todas)</label>
            {isAdmin && (
              <Link to="/administracion/conexiones-api" className={formStyles.manageLink}>
                <Settings size={12} /> Gestionar tablas
              </Link>
            )}
          </div>
          <TagMultiSelect id="tables" options={tables} selected={selectedTables} onChange={setSelectedTables} />
        </div>
        <div className={formStyles.grid}>
          <div className={formStyles.field}>
            <label htmlFor="mode">Modo</label>
            <select id="mode" value={mode} onChange={(e) => setMode(e.target.value as "full" | "incremental")}>
              <option value="full">full</option>
              <option value="incremental">incremental</option>
            </select>
          </div>
          <div className={formStyles.field}>
            <label htmlFor="parallel">Hilos en paralelo</label>
            <input
              id="parallel"
              type="number"
              min={1}
              value={parallel}
              onChange={(e) => setParallel(Number(e.target.value))}
            />
          </div>
        </div>
        <div className={formStyles.field}>
          <label htmlFor="output_dir">Directorio de salida</label>
          <input id="output_dir" type="text" value={outputDir} onChange={(e) => setOutputDir(e.target.value)} />
        </div>
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={resetAll} disabled={!isAdmin} onChange={(e) => setResetAll(e.target.checked)} />
          <span>Resetear TODOS los checkpoints antes de extraer{!isAdmin && " (requiere rol Admin)"}</span>
        </label>
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          <span>Modo simulación (no llama a la API, no descarga nada)</span>
        </label>
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={verbose} onChange={(e) => setVerbose(e.target.checked)} />
          <span>Log detallado</span>
        </label>
        <NotifyCheckbox checked={notify} onChange={setNotify} />
        <button type="submit" className={formStyles.submit} disabled={isSubmitting || isReader}>
          {isSubmitting ? "Ejecutando…" : "Ejecutar extracción Factorial"}
        </button>
      </form>
    </section>
  );
}
