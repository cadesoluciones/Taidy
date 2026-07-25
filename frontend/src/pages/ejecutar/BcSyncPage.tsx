import { useEffect, useState } from "react";

import { ROLE_READER } from "../../api/auth";
import { ApiError } from "../../api/client";
import { fetchBcTables } from "../../api/meta";
import { syncBc } from "../../api/tasks";
import { useAuth } from "../../auth/AuthContext";
import formStyles from "../../components/Form.module.css";
import { NotifyCheckbox } from "../../components/NotifyCheckbox";
import { ReadOnlyNotice } from "../../components/ReadOnlyNotice";

export function BcSyncPage() {
  const { user } = useAuth();
  const isReader = user?.role === ROLE_READER;
  const [tables, setTables] = useState<string[]>([]);
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [mode, setMode] = useState<"incremental" | "full">("incremental");
  const [parallel, setParallel] = useState(1);
  const [outputDir, setOutputDir] = useState("./exports");
  const [dryRun, setDryRun] = useState(false);
  const [skipExisting, setSkipExisting] = useState(false);
  const [verbose, setVerbose] = useState(false);
  const [notify, setNotify] = useState(false);

  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchBcTables()
      .then((res) => setTables(res.items))
      .catch(() => setTables([]));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSuccess(null);
    setError(null);
    setIsSubmitting(true);
    try {
      const task = await syncBc({
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
      <h1>Extraer + subir Business Central en un paso</h1>
      {success && <div className={formStyles.successBanner}>{success}</div>}
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {isReader && <ReadOnlyNotice action="lanzar sincronizaciones" />}
      <form className={formStyles.card} onSubmit={handleSubmit}>
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
            <label htmlFor="mode">Modo</label>
            <select id="mode" value={mode} onChange={(e) => setMode(e.target.value as "incremental" | "full")}>
              <option value="incremental">incremental</option>
              <option value="full">full</option>
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
        <button type="submit" className={formStyles.submit} disabled={isSubmitting || isReader}>
          {isSubmitting ? "Ejecutando…" : "Ejecutar sync BC"}
        </button>
      </form>
    </section>
  );
}
