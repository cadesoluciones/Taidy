import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Settings } from "lucide-react";

import { ROLE_ADMIN, ROLE_READER } from "../../api/auth";
import { ApiError } from "../../api/client";
import { fetchFactorialTables } from "../../api/meta";
import { uploadFactorial } from "../../api/tasks";
import { useAuth } from "../../auth/AuthContext";
import formStyles from "../../components/Form.module.css";
import { NotifyCheckbox } from "../../components/NotifyCheckbox";
import { ReadOnlyNotice } from "../../components/ReadOnlyNotice";
import { TagMultiSelect } from "../../components/TagMultiSelect";

export function FactorialUploadPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === ROLE_ADMIN;
  const isReader = user?.role === ROLE_READER;
  const [outputDir, setOutputDir] = useState("./exports_factorial");
  const [tables, setTables] = useState<string[]>([]);
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
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
    if (!outputDir.trim()) {
      setError("Indica un directorio de salida.");
      return;
    }
    setIsSubmitting(true);
    try {
      const task = await uploadFactorial({
        output_dir: outputDir.trim(),
        tables: selectedTables.length ? selectedTables : null,
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
      <h1>Subir CSVs de Factorial a Fabric OneLake</h1>
      {success && <div className={formStyles.successBanner}>{success}</div>}
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {isReader && <ReadOnlyNotice action="lanzar subidas" />}
      <form className={formStyles.card} onSubmit={handleSubmit}>
        <div className={formStyles.field}>
          <label htmlFor="output_dir">Directorio con los CSV</label>
          <input id="output_dir" type="text" value={outputDir} onChange={(e) => setOutputDir(e.target.value)} />
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
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          <span>Modo simulación (solo lista los ficheros, no sube nada)</span>
        </label>
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={skipExisting} onChange={(e) => setSkipExisting(e.target.checked)} />
          <span>Omitir ficheros ya subidos</span>
        </label>
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={verbose} onChange={(e) => setVerbose(e.target.checked)} />
          <span>Log detallado</span>
        </label>
        <NotifyCheckbox checked={notify} onChange={setNotify} />
        <button type="submit" className={formStyles.submit} disabled={isSubmitting || isReader}>
          {isSubmitting ? "Ejecutando…" : "Ejecutar subida Factorial"}
        </button>
      </form>
    </section>
  );
}
