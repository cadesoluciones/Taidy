import { useState } from "react";

import { ROLE_READER } from "../../api/auth";
import { ApiError } from "../../api/client";
import { uploadBc } from "../../api/tasks";
import { useAuth } from "../../auth/AuthContext";
import formStyles from "../../components/Form.module.css";
import { NotifyCheckbox } from "../../components/NotifyCheckbox";
import { ReadOnlyNotice } from "../../components/ReadOnlyNotice";

export function BcUploadPage() {
  const { user } = useAuth();
  const isReader = user?.role === ROLE_READER;
  const [outputDir, setOutputDir] = useState("./exports");
  const [dryRun, setDryRun] = useState(false);
  const [skipExisting, setSkipExisting] = useState(false);
  const [verbose, setVerbose] = useState(false);
  const [notify, setNotify] = useState(false);

  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

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
      const task = await uploadBc({
        output_dir: outputDir.trim(),
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
      <h1>Subir CSVs de Business Central a Fabric OneLake</h1>
      {success && <div className={formStyles.successBanner}>{success}</div>}
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {isReader && <ReadOnlyNotice action="lanzar subidas" />}
      <form className={formStyles.card} onSubmit={handleSubmit}>
        <div className={formStyles.field}>
          <label htmlFor="output_dir">Directorio con los CSV</label>
          <input id="output_dir" type="text" value={outputDir} onChange={(e) => setOutputDir(e.target.value)} />
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
          {isSubmitting ? "Ejecutando…" : "Ejecutar subida BC"}
        </button>
      </form>
    </section>
  );
}
