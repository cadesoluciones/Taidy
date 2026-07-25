import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import { fetchFactorialTables } from "../../api/meta";
import { syncFactorial } from "../../api/tasks";
import formStyles from "../../components/Form.module.css";
import { NotifyCheckbox } from "../../components/NotifyCheckbox";

export function FactorialSyncPage() {
  const [startOn, setStartOn] = useState("2025-01-01");
  const [endOn, setEndOn] = useState(new Date().toISOString().slice(0, 10));
  const [employeeStatus, setEmployeeStatus] = useState<"active" | "inactive" | "all">("active");
  const [tables, setTables] = useState<string[]>([]);
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [mode, setMode] = useState<"incremental" | "full">("incremental");
  const [parallel, setParallel] = useState(5);
  const [outputDir, setOutputDir] = useState("./exports_factorial");
  const [dryRun, setDryRun] = useState(false);
  const [skipExisting, setSkipExisting] = useState(false);
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
    setIsSubmitting(true);
    try {
      const task = await syncFactorial({
        start_on: startOn,
        end_on: endOn,
        employee_status: employeeStatus,
        tables: selectedTables.length ? selectedTables : null,
        output_dir: outputDir.trim(),
        mode,
        parallel,
        dry_run: dryRun,
        skip_existing: skipExisting,
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
      <h1>Extraer + subir Factorial en un paso</h1>
      {success && <div className={formStyles.successBanner}>{success}</div>}
      {error && <div className={formStyles.errorBanner}>{error}</div>}
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
            <label htmlFor="mode">Modo</label>
            <select id="mode" value={mode} onChange={(e) => setMode(e.target.value as "incremental" | "full")}>
              <option value="incremental">incremental</option>
              <option value="full">full</option>
            </select>
          </div>
        </div>
        <div className={formStyles.field}>
          <label htmlFor="tables">Tablas (vacío = todas)</label>
          <select
            id="tables"
            multiple
            className={formStyles.multiselect}
            value={selectedTables}
            onChange={(e) => setSelectedTables(Array.from(e.target.selectedOptions, (o) => o.value))}
          >
            {tables.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className={formStyles.grid}>
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
          <div className={formStyles.field}>
            <label htmlFor="output_dir">Directorio de salida</label>
            <input id="output_dir" type="text" value={outputDir} onChange={(e) => setOutputDir(e.target.value)} />
          </div>
        </div>
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          <span>Modo simulación (no hace cambios reales)</span>
        </label>
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={skipExisting} onChange={(e) => setSkipExisting(e.target.checked)} />
          <span>Omitir ficheros ya subidos al subir</span>
        </label>
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={verbose} onChange={(e) => setVerbose(e.target.checked)} />
          <span>Log detallado</span>
        </label>
        <NotifyCheckbox checked={notify} onChange={setNotify} />
        <button type="submit" className={formStyles.submit} disabled={isSubmitting}>
          {isSubmitting ? "Ejecutando…" : "Ejecutar sync Factorial"}
        </button>
      </form>
    </section>
  );
}
