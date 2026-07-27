import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import { fetchSummaryMode, setSummaryMode, type SummaryMode } from "../../api/dashboard";
import formStyles from "../../components/Form.module.css";

export function ConfiguracionPage() {
  const [mode, setMode] = useState<SummaryMode["mode"] | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    fetchSummaryMode().then((res) => setMode(res.mode));
  }, []);

  async function handleChange(newMode: SummaryMode["mode"]) {
    setIsSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await setSummaryMode(newMode);
      setMode(res.mode);
      setSuccess("Guardado.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar el cambio.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section>
      <h1>Configuración</h1>

      <h2>Resumen de actividad (Inicio)</h2>
      <p>
        Cómo se genera el texto del "Resumen de actividad" que ven todos los usuarios en Inicio. La plantilla no tiene
        coste ni depende de ningún servicio externo; la IA generativa necesita un proveedor configurado en el
        servidor (ver <code>.env.example</code>) y, si no lo está o la llamada falla, se usa la plantilla igualmente.
      </p>

      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {success && <div className={formStyles.successBanner}>{success}</div>}

      {mode && (
        <div className={formStyles.card}>
          <label className={formStyles.checkboxField}>
            <input
              type="radio"
              name="config_summary_mode"
              checked={mode === "template"}
              disabled={isSaving}
              onChange={() => void handleChange("template")}
            />
            <span>Plantilla (recomendado, sin coste)</span>
          </label>
          <label className={formStyles.checkboxField}>
            <input
              type="radio"
              name="config_summary_mode"
              checked={mode === "llm"}
              disabled={isSaving}
              onChange={() => void handleChange("llm")}
            />
            <span>IA generativa</span>
          </label>
        </div>
      )}
    </section>
  );
}
