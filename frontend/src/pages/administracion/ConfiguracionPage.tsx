import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import { fetchSummaryMode, setSummaryMode, type SummaryMode } from "../../api/dashboard";
import { fetchFabricCatalog, fetchTypeIcons, setTypeIcon } from "../../api/fabricCatalog";
import formStyles from "../../components/Form.module.css";
import managerStyles from "../../components/FabricCatalogManager.module.css";
import { PageHeader } from "../../components/PageHeader";
import { FABRIC_ICON_OPTIONS } from "../../utils/fabricIcons";

export function ConfiguracionPage() {
  const [mode, setMode] = useState<SummaryMode["mode"] | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [types, setTypes] = useState<string[]>([]);
  const [typeIcons, setTypeIcons] = useState<Record<string, string>>({});
  const [typeIconsError, setTypeIconsError] = useState<string | null>(null);
  const [savingType, setSavingType] = useState<string | null>(null);

  useEffect(() => {
    fetchSummaryMode().then((res) => setMode(res.mode));
  }, []);

  useEffect(() => {
    fetchTypeIcons()
      .then((res) => setTypeIcons(res.icons))
      .catch(() => setTypeIcons({}));
    // The catalog itself is the source of truth for which types actually
    // exist in this tenant right now -- union with whatever's already in
    // typeIcons (from an earlier round, or a type that's since disappeared)
    // so an existing mapping is never silently hidden.
    fetchFabricCatalog()
      .then((res) => setTypes(Array.from(new Set(res.items.map((i) => i.type))).sort((a, b) => a.localeCompare(b))))
      .catch(() => setTypes([]));
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

  async function handleTypeIconChange(type: string, icon: string) {
    setSavingType(type);
    setTypeIconsError(null);
    try {
      const res = await setTypeIcon(type, icon);
      setTypeIcons(res.icons);
    } catch (err) {
      setTypeIconsError(err instanceof ApiError ? err.message : "No se pudo guardar el icono.");
    } finally {
      setSavingType(null);
    }
  }

  const allTypes = Array.from(new Set([...types, ...Object.keys(typeIcons)])).sort((a, b) => a.localeCompare(b));

  return (
    <section>
      <PageHeader title="Configuración" />

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

      <h2>Iconos por tipo de elemento (Gobernanza de datos)</h2>
      <p>
        El icono que se muestra por defecto para cada tipo de elemento del catálogo de Fabric (filtros rápidos y
        bloques que no tienen un icono propio elegido a mano en su ficha).
      </p>

      {typeIconsError && <div className={formStyles.errorBanner}>{typeIconsError}</div>}

      {allTypes.length === 0 ? (
        <p className={formStyles.hint}>Todavía no se ha cargado ningún tipo de elemento.</p>
      ) : (
        <div className={formStyles.card}>
          {allTypes.map((type) => {
            const current = typeIcons[type] ?? "";
            return (
              <div key={type} className={managerStyles.compactField} style={{ marginBottom: "var(--space-3)" }}>
                <span className={managerStyles.compactLabel}>{type}</span>
                <div className={managerStyles.iconGrid}>
                  {FABRIC_ICON_OPTIONS.map(({ key, label, Icon }) => (
                    <button
                      key={key}
                      type="button"
                      title={label}
                      disabled={savingType === type}
                      className={current === key ? managerStyles.iconActive : managerStyles.iconOption}
                      onClick={() => void handleTypeIconChange(type, key)}
                    >
                      <Icon size={14} />
                    </button>
                  ))}
                  {current && (
                    <button
                      type="button"
                      title="Sin icono por defecto"
                      disabled={savingType === type}
                      className={managerStyles.iconOption}
                      onClick={() => void handleTypeIconChange(type, "")}
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
