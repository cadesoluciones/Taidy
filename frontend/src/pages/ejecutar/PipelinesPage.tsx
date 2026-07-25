import { useEffect, useState } from "react";

import { ROLE_READER } from "../../api/auth";
import { ApiError } from "../../api/client";
import { fetchPipelines } from "../../api/meta";
import { runPipeline } from "../../api/tasks";
import { useAuth } from "../../auth/AuthContext";
import formStyles from "../../components/Form.module.css";
import { NotifyCheckbox } from "../../components/NotifyCheckbox";
import { ReadOnlyNotice } from "../../components/ReadOnlyNotice";

export function PipelinesPage() {
  const { user } = useAuth();
  const isReader = user?.role === ROLE_READER;
  const [pipelines, setPipelines] = useState<string[]>([]);
  const [pipeline, setPipeline] = useState("");
  const [wait, setWait] = useState(true);
  const [pollSeconds, setPollSeconds] = useState(15);
  const [verbose, setVerbose] = useState(false);
  const [notify, setNotify] = useState(false);

  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchPipelines()
      .then((res) => {
        setPipelines(res.items);
        setPipeline(res.items[0] ?? "");
      })
      .catch(() => setPipelines([]));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSuccess(null);
    setError(null);
    setIsSubmitting(true);
    try {
      const task = await runPipeline({ pipeline, wait, poll_seconds: pollSeconds, verbose, notify });
      setSuccess(`Tarea iniciada (${task.id.slice(0, 8)}). Sigue el progreso en Tareas en curso.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo lanzar el pipeline.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section>
      <h1>Ejecutar un pipeline de Fabric Data Factory</h1>
      {success && <div className={formStyles.successBanner}>{success}</div>}
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {isReader && <ReadOnlyNotice action="lanzar pipelines" />}
      {pipelines.length === 0 ? (
        <p>
          No hay pipelines configurados todavía. Añade entradas en la sección <code>fabric_pipelines.pipelines</code>{" "}
          de <code>config.json</code> (nombre + item_id de Fabric).
        </p>
      ) : (
        <form className={formStyles.card} onSubmit={handleSubmit}>
          <div className={formStyles.field}>
            <label htmlFor="pipeline">Pipeline</label>
            <select id="pipeline" value={pipeline} onChange={(e) => setPipeline(e.target.value)}>
              {pipelines.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <label className={formStyles.checkboxField}>
            <input type="checkbox" checked={wait} onChange={(e) => setWait(e.target.checked)} />
            <span>Esperar y seguir el estado en vivo (recomendado)</span>
          </label>
          <div className={formStyles.field}>
            <label htmlFor="poll_seconds">Cada cuántos segundos consultar el estado</label>
            <input
              id="poll_seconds"
              type="number"
              min={5}
              value={pollSeconds}
              onChange={(e) => setPollSeconds(Number(e.target.value))}
            />
          </div>
          <label className={formStyles.checkboxField}>
            <input type="checkbox" checked={verbose} onChange={(e) => setVerbose(e.target.checked)} />
            <span>Log detallado</span>
          </label>
          <NotifyCheckbox checked={notify} onChange={setNotify} />
          <button type="submit" className={formStyles.submit} disabled={isSubmitting || isReader}>
            {isSubmitting ? "Lanzando…" : "Lanzar pipeline"}
          </button>
          <p className={formStyles.hint}>
            Detener el seguimiento aquí NO cancela el pipeline en Fabric — solo deja de consultarlo. Para cancelarlo
            de verdad, hazlo desde el propio portal de Fabric.
          </p>
        </form>
      )}
    </section>
  );
}
