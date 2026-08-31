import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Settings } from "lucide-react";

import { ApiError } from "../../api/client";
import { fetchBcTables } from "../../api/meta";
import { extractBc } from "../../api/tasks";
import { ROLE_ADMIN, ROLE_READER } from "../../api/auth";
import { useAuth } from "../../auth/AuthContext";
import formStyles from "../../components/Form.module.css";
import { NotifyCheckbox } from "../../components/NotifyCheckbox";
import { PageHeader } from "../../components/PageHeader";
import { ReadOnlyNotice } from "../../components/ReadOnlyNotice";
import { TagMultiSelect } from "../../components/TagMultiSelect";

export function BcExtractPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === ROLE_ADMIN;
  const isReader = user?.role === ROLE_READER;

  const [tables, setTables] = useState<string[]>([]);
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [mode, setMode] = useState<"incremental" | "full">("incremental");
  const [parallel, setParallel] = useState(1);
  const [outputDir, setOutputDir] = useState("./exports");
  const [pageSize, setPageSize] = useState(0);
  const [checkpointPath, setCheckpointPath] = useState("");
  const [dryRun, setDryRun] = useState(false);
  const [resetWatermarks, setResetWatermarks] = useState(false);
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
      const task = await extractBc({
        tables: selectedTables.length ? selectedTables : null,
        output_dir: outputDir.trim(),
        page_size: pageSize || null,
        mode,
        parallel,
        dry_run: dryRun,
        reset_watermarks: resetWatermarks,
        checkpoint_path: checkpointPath.trim(),
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
      <PageHeader title="Extraer tablas de Business Central" />
      {success && <div className={formStyles.successBanner}>{success}</div>}
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {isReader && <ReadOnlyNotice action="lanzar extracciones" />}
      <form className={formStyles.card} onSubmit={handleSubmit}>
        <div className={formStyles.grid}>
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
          <div className={formStyles.field}>
            <label htmlFor="mode">Modo</label>
            <select id="mode" value={mode} onChange={(e) => setMode(e.target.value as "incremental" | "full")}>
              <option value="incremental">incremental</option>
              <option value="full">full</option>
            </select>
          </div>
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
        <div className={formStyles.grid}>
          <div className={formStyles.field}>
            <label htmlFor="page_size">Tamaño de página (0 = config.json)</label>
            <input
              id="page_size"
              type="number"
              min={0}
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
            />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="checkpoint_path">Ruta de checkpoints en OneLake</label>
            <input
              id="checkpoint_path"
              type="text"
              value={checkpointPath}
              onChange={(e) => setCheckpointPath(e.target.value)}
            />
          </div>
        </div>

        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          <span>Modo simulación (no llama a la API, no descarga nada)</span>
        </label>
        <label className={formStyles.checkboxField}>
          <input
            type="checkbox"
            checked={resetWatermarks}
            disabled={!isAdmin}
            onChange={(e) => setResetWatermarks(e.target.checked)}
          />
          <span>Resetear checkpoints antes de extraer{!isAdmin && " (requiere rol Admin)"}</span>
        </label>
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={verbose} onChange={(e) => setVerbose(e.target.checked)} />
          <span>Log detallado (verbose)</span>
        </label>
        <NotifyCheckbox checked={notify} onChange={setNotify} />

        <button type="submit" className={formStyles.submit} disabled={isSubmitting || isReader}>
          {isSubmitting ? "Ejecutando…" : "Ejecutar extracción BC"}
        </button>
      </form>
    </section>
  );
}
