import { useEffect, useState } from "react";
import { Eye, EyeOff, Save } from "lucide-react";

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
import formStyles from "../../components/Form.module.css";
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

  useEffect(() => {
    fetchSecrets()
      .then((res) => {
        setFields(res.items);
        setDrafts(Object.fromEntries(res.items.map((f) => [f.key, f.value])));
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "No se pudieron cargar las claves."));
  }, []);

  const groups = [...new Set(fields.map((f) => f.group))];

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
      <h1>Claves de servicio</h1>
      <p>
        Valores de <code>.env</code> — se autorrellenan con lo que ya hay configurado en el servidor. Por defecto
        se muestran ocultos; usa el icono del ojo para verlos. Guardar aquí escribe directamente en{" "}
        <code>.env</code> y aplica el cambio de inmediato para las próximas ejecuciones. "Probar acceso" solo hace
        una lectura mínima real (nunca crea, modifica ni borra nada) para confirmar que la clave funciona.
      </p>

      {error && <div className={formStyles.errorBanner}>{error}</div>}

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
          </div>
        );
      })}
    </section>
  );
}
