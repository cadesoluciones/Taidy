import { useEffect, useState } from "react";
import { Eye, EyeOff, Save, X } from "lucide-react";

import {
  fetchConfigFields,
  fetchPipelines,
  setPipelines as saveRemotePipelines,
  updateConfigField,
  type ConfigField,
  type ConfigFieldValue,
  type Pipeline,
} from "../../api/configSettings";
import { ApiError } from "../../api/client";
import {
  fetchSecrets,
  testBusinessCentral,
  testFabric,
  testFactorial,
  testHubspot,
  updateSecret,
  type EnvField,
  type TestConnectionResult,
} from "../../api/secrets";
import { FreeTagInput } from "../../components/FreeTagInput";
import formStyles from "../../components/Form.module.css";
import { PageHeader } from "../../components/PageHeader";
import styles from "./SecretsPage.module.css";

const TEST_FUNCTIONS: Record<string, () => Promise<TestConnectionResult>> = {
  "Business Central": testBusinessCentral,
  "Factorial HR": testFactorial,
  "HubSpot CRM": testHubspot,
  "Fabric OneLake": testFabric,
};

export function SecretsPage() {
  const [fields, setFields] = useState<EnvField[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestConnectionResult | undefined>>({});
  const [testingGroup, setTestingGroup] = useState<string | null>(null);

  // config.json's own non-secret connection parameters (tenant/client/
  // workspace/lakehouse ids, retry/paging tuning, notifications) -- kept
  // as a separate source from the .env-backed `fields` above (different
  // API, different value types) but rendered into the SAME per-group
  // cards below, so e.g. "Fabric OneLake" shows FABRIC_CLIENT_SECRET
  // alongside the workspace/lakehouse ids in one place.
  const [configFields, setConfigFields] = useState<ConfigField[]>([]);
  const [configDrafts, setConfigDrafts] = useState<Record<string, ConfigFieldValue>>({});
  const [savingConfigKey, setSavingConfigKey] = useState<string | null>(null);
  const [savedConfigKey, setSavedConfigKey] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  // fabric_pipelines.pipelines -- a list, not a scalar field, so it gets
  // its own small add/remove editor instead of a slot in configFields.
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipelinesDraft, setPipelinesDraft] = useState<Pipeline[]>([]);
  const [pipelinesSaving, setPipelinesSaving] = useState(false);
  const [pipelinesSaved, setPipelinesSaved] = useState(false);
  const [pipelinesError, setPipelinesError] = useState<string | null>(null);

  useEffect(() => {
    fetchSecrets()
      .then((res) => {
        setFields(res.items);
        setDrafts(Object.fromEntries(res.items.map((f) => [f.key, f.value])));
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "No se pudieron cargar las claves."));

    fetchConfigFields()
      .then((res) => {
        setConfigFields(res.items);
        setConfigDrafts(Object.fromEntries(res.items.map((f) => [f.key, f.value])));
      })
      .catch((err) => setConfigError(err instanceof ApiError ? err.message : "No se pudieron cargar los parámetros."));

    fetchPipelines()
      .then((res) => {
        setPipelines(res.items);
        setPipelinesDraft(res.items);
      })
      .catch((err) => setPipelinesError(err instanceof ApiError ? err.message : "No se pudieron cargar los pipelines."));
  }, []);

  const groups = [...new Set([...fields.map((f) => f.group), ...configFields.map((f) => f.group)])];

  async function handleSaveConfig(key: string) {
    setConfigError(null);
    setSavedConfigKey(null);
    setSavingConfigKey(key);
    try {
      const updated = await updateConfigField(key, configDrafts[key] ?? "");
      setConfigFields((prev) => prev.map((f) => (f.key === key ? updated : f)));
      setSavedConfigKey(key);
    } catch (err) {
      setConfigError(err instanceof ApiError ? err.message : "No se pudo guardar.");
    } finally {
      setSavingConfigKey(null);
    }
  }

  function updatePipelineDraft(index: number, patch: Partial<Pipeline>) {
    setPipelinesSaved(false);
    setPipelinesDraft((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  async function handleSavePipelines() {
    setPipelinesError(null);
    setPipelinesSaved(false);
    setPipelinesSaving(true);
    try {
      const cleaned = pipelinesDraft.filter((p) => p.name.trim() || p.item_id.trim());
      const result = await saveRemotePipelines(cleaned);
      setPipelines(result.items);
      setPipelinesDraft(result.items);
      setPipelinesSaved(true);
    } catch (err) {
      setPipelinesError(err instanceof ApiError ? err.message : "No se pudieron guardar los pipelines.");
    } finally {
      setPipelinesSaving(false);
    }
  }

  const pipelinesDirty = JSON.stringify(pipelinesDraft) !== JSON.stringify(pipelines);

  async function handleSave(key: string) {
    setError(null);
    setSavedKey(null);
    setSavingKey(key);
    try {
      const updated = await updateSecret(key, drafts[key] ?? "");
      setFields((prev) => prev.map((f) => (f.key === key ? updated : f)));
      setSavedKey(key);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar.");
    } finally {
      setSavingKey(null);
    }
  }

  async function handleTest(group: string) {
    const fn = TEST_FUNCTIONS[group];
    if (!fn) return;
    setTestingGroup(group);
    setTestResults((prev) => ({ ...prev, [group]: undefined }));
    try {
      const result = await fn();
      setTestResults((prev) => ({ ...prev, [group]: result }));
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [group]: { ok: false, message: err instanceof ApiError ? err.message : "Error al probar la conexión." },
      }));
    } finally {
      setTestingGroup(null);
    }
  }

  return (
    <section>
      <PageHeader
        title="Claves de servicio"
        description={
          <>
            Secretos de <code>.env</code> y parámetros de <code>config.json</code> (tenant, cliente, workspace,
            Lakehouse…) — todo se autorrellena con lo que ya hay configurado en el servidor, y nada queda solo
            editable a mano en el fichero. Los secretos se muestran ocultos por defecto; usa el icono del ojo para
            verlos. Cada campo se guarda por separado con su propio icono. "Probar acceso" solo hace una lectura
            mínima real (nunca crea, modifica ni borra nada) para confirmar que la conexión funciona.
          </>
        }
      />

      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {configError && <div className={formStyles.errorBanner}>{configError}</div>}

      {groups.map((group) => {
        const groupFields = fields.filter((f) => f.group === group);
        const testFn = TEST_FUNCTIONS[group];
        const result = testResults[group];
        return (
          <div key={group} className={formStyles.card} style={{ maxWidth: "none", marginBottom: "var(--space-4)" }}>
            <div className={styles.groupHeader}>
              <h2>{group}</h2>
              {testFn && (
                <button
                  type="button"
                  className={formStyles.submit}
                  disabled={testingGroup === group}
                  onClick={() => handleTest(group)}
                >
                  {testingGroup === group ? "Probando…" : "Probar acceso"}
                </button>
              )}
            </div>

            {result && (
              <div className={result.ok ? formStyles.successBanner : formStyles.errorBanner}>{result.message}</div>
            )}

            {groupFields.map((f) => {
              const isRevealed = revealed[f.key] ?? false;
              const dirty = (drafts[f.key] ?? "") !== f.value;
              return (
                <div className={formStyles.field} key={f.key}>
                  <label htmlFor={`secret_${f.key}`}>{f.label}</label>
                  <div className={styles.fieldRow}>
                    <input
                      id={`secret_${f.key}`}
                      type={f.secret && !isRevealed ? "password" : "text"}
                      value={drafts[f.key] ?? ""}
                      onChange={(e) => {
                        setSavedKey(null);
                        setDrafts((prev) => ({ ...prev, [f.key]: e.target.value }));
                      }}
                    />
                    {f.secret && (
                      <button
                        type="button"
                        className={styles.iconBtn}
                        aria-label={isRevealed ? "Ocultar clave" : "Mostrar clave"}
                        onClick={() => setRevealed((prev) => ({ ...prev, [f.key]: !prev[f.key] }))}
                      >
                        {isRevealed ? <EyeOff size={15} /> : <Eye size={15} />}
                      </button>
                    )}
                    <button
                      type="button"
                      className={styles.iconBtn}
                      aria-label="Guardar"
                      disabled={!dirty || savingKey === f.key}
                      onClick={() => handleSave(f.key)}
                    >
                      <Save size={15} />
                    </button>
                  </div>
                  {savedKey === f.key && <p className={formStyles.hint}>Guardado.</p>}
                </div>
              );
            })}

            {configFields
              .filter((f) => f.group === group)
              .map((f) => {
                const dirty = JSON.stringify(configDrafts[f.key]) !== JSON.stringify(f.value);
                return (
                  <div className={formStyles.field} key={f.key}>
                    <label htmlFor={`config_${f.key}`}>{f.label}</label>
                    <div className={styles.fieldRow}>
                      {f.kind === "boolean" ? (
                        <input
                          id={`config_${f.key}`}
                          type="checkbox"
                          checked={Boolean(configDrafts[f.key])}
                          onChange={(e) => {
                            setSavedConfigKey(null);
                            setConfigDrafts((prev) => ({ ...prev, [f.key]: e.target.checked }));
                          }}
                        />
                      ) : f.kind === "list" ? (
                        <FreeTagInput
                          id={`config_${f.key}`}
                          selected={(configDrafts[f.key] as string[] | undefined) ?? []}
                          onChange={(next) => {
                            setSavedConfigKey(null);
                            setConfigDrafts((prev) => ({ ...prev, [f.key]: next }));
                          }}
                          placeholder="correo@empresa.com"
                          emptyHint="Sin destinatarios"
                        />
                      ) : (
                        <input
                          id={`config_${f.key}`}
                          type={f.kind === "number" ? "number" : "text"}
                          value={String(configDrafts[f.key] ?? "")}
                          onChange={(e) => {
                            setSavedConfigKey(null);
                            const raw = e.target.value;
                            const next: ConfigFieldValue = f.kind === "number" ? (raw === "" ? "" : Number(raw)) : raw;
                            setConfigDrafts((prev) => ({ ...prev, [f.key]: next }));
                          }}
                        />
                      )}
                      <button
                        type="button"
                        className={styles.iconBtn}
                        aria-label="Guardar"
                        disabled={!dirty || savingConfigKey === f.key}
                        onClick={() => handleSaveConfig(f.key)}
                      >
                        <Save size={15} />
                      </button>
                    </div>
                    {savedConfigKey === f.key && <p className={formStyles.hint}>Guardado.</p>}
                  </div>
                );
              })}
          </div>
        );
      })}

      <div className={formStyles.card} style={{ maxWidth: "none", marginBottom: "var(--space-4)" }}>
        <div className={styles.groupHeader}>
          <h2>Fabric — Pipelines</h2>
        </div>
        <p className={formStyles.hint}>
          Los pipelines de Fabric Data Factory que "Flujos" puede lanzar por nombre, con el item_id real de cada uno
          en el workspace.
        </p>
        {pipelinesError && <div className={formStyles.errorBanner}>{pipelinesError}</div>}
        {pipelinesDraft.map((p, i) => (
          <div className={styles.fieldRow} key={i} style={{ marginBottom: "var(--space-2)" }}>
            <input
              type="text"
              placeholder="Nombre (ej. Pipeline_CADE_Gold)"
              value={p.name}
              onChange={(e) => updatePipelineDraft(i, { name: e.target.value })}
            />
            <input
              type="text"
              placeholder="item_id"
              value={p.item_id}
              onChange={(e) => updatePipelineDraft(i, { item_id: e.target.value })}
            />
            <button
              type="button"
              className={styles.iconBtn}
              aria-label={`Quitar ${p.name || "pipeline"}`}
              onClick={() => {
                setPipelinesSaved(false);
                setPipelinesDraft((prev) => prev.filter((_, j) => j !== i));
              }}
            >
              <X size={15} />
            </button>
          </div>
        ))}
        <div className={styles.groupHeader}>
          <button
            type="button"
            className={styles.iconBtn}
            aria-label="Añadir pipeline"
            onClick={() => {
              setPipelinesSaved(false);
              setPipelinesDraft((prev) => [...prev, { name: "", item_id: "" }]);
            }}
          >
            +
          </button>
          <button
            type="button"
            className={formStyles.submit}
            disabled={pipelinesSaving || !pipelinesDirty}
            onClick={() => void handleSavePipelines()}
          >
            {pipelinesSaving ? "Guardando…" : "Guardar pipelines"}
          </button>
        </div>
        {pipelinesSaved && <p className={formStyles.hint}>Guardado.</p>}
      </div>
    </section>
  );
}
