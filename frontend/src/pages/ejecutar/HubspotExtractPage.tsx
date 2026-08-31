import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Settings } from "lucide-react";

import { ROLE_ADMIN, ROLE_READER } from "../../api/auth";
import { ApiError } from "../../api/client";
import { fetchHubspotTables } from "../../api/meta";
import { extractHubspot } from "../../api/tasks";
import { useAuth } from "../../auth/AuthContext";
import formStyles from "../../components/Form.module.css";
import { NotifyCheckbox } from "../../components/NotifyCheckbox";
import { PageHeader } from "../../components/PageHeader";
import { ReadOnlyNotice } from "../../components/ReadOnlyNotice";
import { TagMultiSelect } from "../../components/TagMultiSelect";

export function HubspotExtractPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === ROLE_ADMIN;
  const isReader = user?.role === ROLE_READER;

  const [tables, setTables] = useState<string[]>([]);
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [parallel, setParallel] = useState(1);
  const [outputDir, setOutputDir] = useState("./exports_hubspot");
  const [dryRun, setDryRun] = useState(false);
  const [verbose, setVerbose] = useState(false);
  const [notify, setNotify] = useState(false);

  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchHubspotTables()
      .then((res) => setTables(res.items))
      .catch(() => setTables([]));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSuccess(null);
    setError(null);

    setIsSubmitting(true);
    try {
      const task = await extractHubspot({
        tables: selectedTables.length ? selectedTables : null,
        output_dir: outputDir.trim(),
        parallel,
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
      <PageHeader title="Extraer objetos de HubSpot" />
      {success && <div className={formStyles.successBanner}>{success}</div>}
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {isReader && <ReadOnlyNotice action="lanzar extracciones" />}
      <form className={formStyles.card} onSubmit={handleSubmit}>
        <div className={formStyles.field}>
          <div className={formStyles.labelRow}>
            <label htmlFor="tables">Objetos (vacío = todos: contactos, empresas, oportunidades)</label>
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
          <span>Modo simulación (no llama a la API, no descarga nada)</span>
        </label>
        <label className={formStyles.checkboxField}>
          <input type="checkbox" checked={verbose} onChange={(e) => setVerbose(e.target.checked)} />
          <span>Log detallado</span>
        </label>
        <NotifyCheckbox checked={notify} onChange={setNotify} />
        <button type="submit" className={formStyles.submit} disabled={isSubmitting || isReader}>
          {isSubmitting ? "Ejecutando…" : "Ejecutar extracción HubSpot"}
        </button>
      </form>
    </section>
  );
}
