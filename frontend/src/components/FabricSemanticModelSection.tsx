import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import {
  createSemanticModel,
  fetchSemanticModelState,
  syncSemanticModelColumns,
  updateSemanticModelDescriptions,
  type SemanticModelState,
} from "../api/fabricCatalog";
import { ConfirmDialog } from "./ConfirmDialog";
import styles from "./FabricSemanticModelSection.module.css";
import formStyles from "./Form.module.css";

interface FabricSemanticModelSectionProps {
  itemId: string;
  itemName: string;
  canEdit: boolean;
}

/** A Fabric semantic model's column structure (name/type) is always
 * auto-detected from the real table -- create/sync never ask the user to
 * type a column by hand, only descriptions are editable here. See
 * webapp/fabric_catalog.py's create_semantic_model()/sync_semantic_model_columns()
 * and src/fabric_pipelines/semantic_model_tmdl.py for how that's built. */
export function FabricSemanticModelSection({ itemId, itemName, canEdit }: FabricSemanticModelSectionProps) {
  const [state, setState] = useState<SemanticModelState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [descDrafts, setDescDrafts] = useState<Record<string, string>>({});
  const [confirmCreateOpen, setConfirmCreateOpen] = useState(false);

  function applyState(result: SemanticModelState) {
    setState(result);
    setDescDrafts(Object.fromEntries(result.columns.map((c) => [c.name, c.description])));
  }

  async function load() {
    setIsLoading(true);
    setError(null);
    try {
      applyState(await fetchSemanticModelState(itemId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo leer el modelo semántico.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemId]);

  async function handleCreate() {
    setConfirmCreateOpen(false);
    setBusy(true);
    setError(null);
    try {
      applyState(await createSemanticModel(itemId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear el modelo semántico.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSync() {
    setBusy(true);
    setError(null);
    try {
      const result = await syncSemanticModelColumns(itemId);
      setState(result);
      // Keep any description the user already typed but hasn't saved yet --
      // only fill in the newly-synced columns, don't clobber a live edit.
      setDescDrafts((prev) => ({
        ...Object.fromEntries(result.columns.map((c) => [c.name, c.description])),
        ...prev,
      }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudieron sincronizar las columnas.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveDescriptions() {
    if (!state) return;
    const changed: Record<string, string> = {};
    for (const col of state.columns) {
      const draft = descDrafts[col.name] ?? "";
      if (draft !== col.description) changed[col.name] = draft;
    }
    if (Object.keys(changed).length === 0) return;
    setBusy(true);
    setError(null);
    try {
      applyState(await updateSemanticModelDescriptions(itemId, changed));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudieron guardar las descripciones.");
    } finally {
      setBusy(false);
    }
  }

  const isDirty = !!state && state.columns.some((c) => (descDrafts[c.name] ?? "") !== c.description);

  // Fabric's own getDefinition call can be a long-running operation right
  // after a model is created/edited (confirmed live: up to ~20s) -- setting
  // that expectation beats a spinner that looks stuck.
  if (isLoading) return <p className={formStyles.hint}>Cargando modelo semántico… puede tardar unos segundos.</p>;

  return (
    <div className={styles.wrap}>
      {error && <div className={formStyles.errorBanner}>{error}</div>}

      {!state?.linked ? (
        <div>
          <p className={formStyles.hint}>
            Esta tabla todavía no tiene un modelo semántico en Fabric.
            {state && state.missing_columns.length > 0 && (
              <> Se creará en modo DirectLake con sus {state.missing_columns.length} columnas detectadas automáticamente.</>
            )}
          </p>
          {canEdit && (
            <button
              type="button"
              className={`${formStyles.submit} no-print`}
              disabled={busy}
              onClick={() => setConfirmCreateOpen(true)}
            >
              Crear modelo semántico
            </button>
          )}
        </div>
      ) : (
        <div>
          <p className={styles.modelName}>
            Modelo: <strong>{state.model_name}</strong>
          </p>
          {state.missing_columns.length > 0 && (
            <div className={`${styles.syncHint} no-print`}>
              <span>
                {state.missing_columns.length} columna(s) nueva(s) detectada(s) en la tabla que el modelo todavía no tiene.
              </span>
              {canEdit && (
                <button type="button" className={styles.linkButton} disabled={busy} onClick={() => void handleSync()}>
                  Añadirlas ahora
                </button>
              )}
            </div>
          )}
          {state.columns.length > 0 ? (
            <table className={styles.columnsTable}>
              <thead>
                <tr>
                  <th>Columna</th>
                  <th>Descripción</th>
                </tr>
              </thead>
              <tbody>
                {state.columns.map((col) => (
                  <tr key={col.name}>
                    <td>
                      {col.name}
                      {!col.in_source && (
                        <span className={styles.staleBadge} title="Ya no existe en la tabla real">
                          obsoleta
                        </span>
                      )}
                    </td>
                    <td>
                      {canEdit ? (
                        <input
                          type="text"
                          className={styles.descInput}
                          value={descDrafts[col.name] ?? ""}
                          onChange={(e) => setDescDrafts((prev) => ({ ...prev, [col.name]: e.target.value }))}
                        />
                      ) : (
                        col.description || <em>—</em>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className={formStyles.hint}>El modelo no tiene ninguna columna todavía.</p>
          )}
          {canEdit && (
            <button
              type="button"
              className={`${formStyles.submit} no-print`}
              disabled={busy || !isDirty}
              onClick={() => void handleSaveDescriptions()}
            >
              Guardar descripciones
            </button>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmCreateOpen}
        title="Crear modelo semántico"
        description={`Se creará en Fabric un modelo semántico nuevo (DirectLake, una sola tabla) para "${itemName}", con sus columnas detectadas automáticamente a partir de la tabla real.`}
        confirmLabel="Crear"
        danger={false}
        busy={busy}
        onConfirm={handleCreate}
        onCancel={() => setConfirmCreateOpen(false)}
      />
    </div>
  );
}
