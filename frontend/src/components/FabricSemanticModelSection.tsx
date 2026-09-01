import { useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import {
  createSemanticModel,
  fetchSemanticModelState,
  MANUAL_DATA_TYPES,
  setManualSemanticModelColumns,
  syncSemanticModelColumns,
  updateSemanticModelDescriptions,
  type ManualColumn,
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

const DATA_TYPE_LABELS: Record<string, string> = {
  string: "Texto",
  int64: "Entero",
  double: "Decimal",
  boolean: "Sí/No",
  dateTime: "Fecha",
};

/** One row of "name + type" plus an add button, used to build up a manual
 * model's column list -- either as a pure local draft (before the model
 * exists) or committing straight to the API (adding to one that already
 * does, see ManualColumnsEditor usage below). */
function ColumnBuilderRow({
  onAdd,
  disabled,
  existingNames,
}: {
  onAdd: (col: ManualColumn) => void;
  disabled: boolean;
  existingNames: string[];
}) {
  const [name, setName] = useState("");
  const [dataType, setDataType] = useState<string>(MANUAL_DATA_TYPES[0]);

  const trimmed = name.trim();
  const isDuplicate = trimmed.length > 0 && existingNames.some((n) => n.toLowerCase() === trimmed.toLowerCase());
  const canAdd = trimmed.length > 0 && !isDuplicate && !disabled;

  function submit() {
    if (!canAdd) return;
    onAdd({ name: trimmed, data_type: dataType });
    setName("");
    setDataType(MANUAL_DATA_TYPES[0]);
  }

  return (
    <div className={styles.addRow}>
      <input
        type="text"
        className={styles.colInput}
        placeholder="Nombre de columna"
        value={name}
        disabled={disabled}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            submit();
          }
        }}
      />
      <select className={styles.colSelect} value={dataType} disabled={disabled} onChange={(e) => setDataType(e.target.value)}>
        {MANUAL_DATA_TYPES.map((t) => (
          <option key={t} value={t}>
            {DATA_TYPE_LABELS[t] ?? t}
          </option>
        ))}
      </select>
      <button type="button" className={styles.linkButton} disabled={!canAdd} onClick={submit}>
        + Añadir columna
      </button>
      {isDuplicate && <span className={styles.dupHint}>Ya existe una columna con ese nombre</span>}
    </div>
  );
}

/** A Fabric semantic model backed by a real Lakehouse table always has its
 * column structure (name/type) auto-detected -- create/sync never ask the
 * user to type a column by hand there, only descriptions are editable. For
 * every other catalog item (state.has_real_source === false) there's no
 * live table to read, so the model is a manual data dictionary: columns
 * are typed in by hand and have no connection to real data. See
 * webapp/fabric_catalog.py's create_semantic_model()/set_manual_semantic_model_columns()
 * and src/fabric_pipelines/semantic_model_tmdl.py for how both shapes are built. */
export function FabricSemanticModelSection({ itemId, itemName, canEdit }: FabricSemanticModelSectionProps) {
  const [state, setState] = useState<SemanticModelState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [descDrafts, setDescDrafts] = useState<Record<string, string>>({});
  const [confirmCreateOpen, setConfirmCreateOpen] = useState(false);
  const [draftColumns, setDraftColumns] = useState<ManualColumn[]>([]);

  // Fabric's own read (getDefinition) can take 20s+ -- long enough that the
  // user switches to a different table before a request resolves. Every
  // async handler below captures itemId at call time and checks it against
  // this ref (kept in sync with the prop on every render) before touching
  // state, so a slow response for a table that's no longer selected can
  // never overwrite what's currently on screen. Confirmed live this was a
  // real bug: creating a model for one table, then navigating away before
  // it finished, made the NEXT table opened show up as "linked" too.
  const currentItemIdRef = useRef(itemId);
  currentItemIdRef.current = itemId;

  // Defaults to true (the pre-existing, real-source-only behaviour) while
  // state hasn't loaded yet, so nothing flashes the manual UI for a
  // Lakehouse table during the initial fetch.
  const hasRealSource = state?.has_real_source ?? true;

  function applyState(result: SemanticModelState) {
    setState(result);
    setDescDrafts(Object.fromEntries(result.columns.map((c) => [c.name, c.description])));
  }

  async function load() {
    const requestedItemId = itemId;
    setIsLoading(true);
    setError(null);
    try {
      const result = await fetchSemanticModelState(requestedItemId);
      if (currentItemIdRef.current !== requestedItemId) return;
      applyState(result);
    } catch (err) {
      if (currentItemIdRef.current !== requestedItemId) return;
      setError(err instanceof ApiError ? err.message : "No se pudo leer el modelo semántico.");
    } finally {
      if (currentItemIdRef.current === requestedItemId) setIsLoading(false);
    }
  }

  useEffect(() => {
    setState(null);
    setIsLoading(true);
    setDraftColumns([]);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemId]);

  async function handleCreate() {
    const requestedItemId = itemId;
    const useManual = state?.has_real_source === false;
    setConfirmCreateOpen(false);
    setBusy(true);
    setError(null);
    try {
      const result = useManual
        ? await createSemanticModel(requestedItemId, itemName, draftColumns)
        : await createSemanticModel(requestedItemId);
      if (currentItemIdRef.current !== requestedItemId) return;
      applyState(result);
      setDraftColumns([]);
    } catch (err) {
      if (currentItemIdRef.current !== requestedItemId) return;
      setError(err instanceof ApiError ? err.message : "No se pudo crear el modelo semántico.");
    } finally {
      if (currentItemIdRef.current === requestedItemId) setBusy(false);
    }
  }

  async function handleSync() {
    const requestedItemId = itemId;
    setBusy(true);
    setError(null);
    try {
      const result = await syncSemanticModelColumns(requestedItemId);
      if (currentItemIdRef.current !== requestedItemId) return;
      setState(result);
      // Keep any description the user already typed but hasn't saved yet --
      // only fill in the newly-synced columns, don't clobber a live edit.
      setDescDrafts((prev) => ({
        ...Object.fromEntries(result.columns.map((c) => [c.name, c.description])),
        ...prev,
      }));
    } catch (err) {
      if (currentItemIdRef.current !== requestedItemId) return;
      setError(err instanceof ApiError ? err.message : "No se pudieron sincronizar las columnas.");
    } finally {
      if (currentItemIdRef.current === requestedItemId) setBusy(false);
    }
  }

  async function handleManualColumnsChange(newColumns: ManualColumn[]) {
    const requestedItemId = itemId;
    setBusy(true);
    setError(null);
    try {
      const result = await setManualSemanticModelColumns(requestedItemId, newColumns);
      if (currentItemIdRef.current !== requestedItemId) return;
      setState(result);
      setDescDrafts((prev) => ({
        ...Object.fromEntries(result.columns.map((c) => [c.name, c.description])),
        ...prev,
      }));
    } catch (err) {
      if (currentItemIdRef.current !== requestedItemId) return;
      setError(err instanceof ApiError ? err.message : "No se pudieron actualizar las columnas.");
    } finally {
      if (currentItemIdRef.current === requestedItemId) setBusy(false);
    }
  }

  function handleAddColumn(col: ManualColumn) {
    if (!state) return;
    void handleManualColumnsChange([...state.columns.map((c) => ({ name: c.name, data_type: c.data_type })), col]);
  }

  function handleRemoveColumn(name: string) {
    if (!state) return;
    void handleManualColumnsChange(
      state.columns.filter((c) => c.name !== name).map((c) => ({ name: c.name, data_type: c.data_type }))
    );
  }

  async function handleSaveDescriptions() {
    if (!state) return;
    const requestedItemId = itemId;
    const changed: Record<string, string> = {};
    for (const col of state.columns) {
      const draft = descDrafts[col.name] ?? "";
      if (draft !== col.description) changed[col.name] = draft;
    }
    if (Object.keys(changed).length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await updateSemanticModelDescriptions(requestedItemId, changed);
      if (currentItemIdRef.current !== requestedItemId) return;
      applyState(result);
    } catch (err) {
      if (currentItemIdRef.current !== requestedItemId) return;
      setError(err instanceof ApiError ? err.message : "No se pudieron guardar las descripciones.");
    } finally {
      if (currentItemIdRef.current === requestedItemId) setBusy(false);
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
          {hasRealSource ? (
            <p className={formStyles.hint}>
              Esta tabla todavía no tiene un modelo semántico en Fabric.
              {state && state.missing_columns.length > 0 && (
                <> Se creará en modo DirectLake con sus {state.missing_columns.length} columnas detectadas automáticamente.</>
              )}
            </p>
          ) : (
            <p className={formStyles.hint}>
              Este elemento no es una tabla de Fabric, así que su modelo semántico se define a mano, como diccionario de
              datos -- sin conexión a datos en vivo.
            </p>
          )}

          {canEdit && !hasRealSource && (
            <div className={styles.draftList}>
              {draftColumns.length > 0 && (
                <ul className={styles.draftColumns}>
                  {draftColumns.map((col) => (
                    <li key={col.name}>
                      <span>{col.name}</span>
                      <span className={styles.typeTag}>{DATA_TYPE_LABELS[col.data_type] ?? col.data_type}</span>
                      <button
                        type="button"
                        className={styles.removeButton}
                        onClick={() => setDraftColumns((prev) => prev.filter((c) => c.name !== col.name))}
                        aria-label={`Quitar ${col.name}`}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <ColumnBuilderRow
                onAdd={(col) => setDraftColumns((prev) => [...prev, col])}
                disabled={busy}
                existingNames={draftColumns.map((c) => c.name)}
              />
            </div>
          )}

          {canEdit && (
            <button
              type="button"
              className={`${formStyles.submit} no-print`}
              disabled={busy || (!hasRealSource && draftColumns.length === 0)}
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
          {!hasRealSource && (
            <p className={formStyles.hint}>Diccionario de datos manual -- sin conexión a datos en vivo.</p>
          )}
          {hasRealSource && state.missing_columns.length > 0 && (
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
                  {!hasRealSource && <th>Tipo</th>}
                  <th>Descripción</th>
                  {canEdit && !hasRealSource && <th />}
                </tr>
              </thead>
              <tbody>
                {state.columns.map((col) => (
                  <tr key={col.name}>
                    <td>
                      {col.name}
                      {hasRealSource && !col.in_source && (
                        <span className={styles.staleBadge} title="Ya no existe en la tabla real">
                          obsoleta
                        </span>
                      )}
                    </td>
                    {!hasRealSource && <td>{DATA_TYPE_LABELS[col.data_type] ?? col.data_type}</td>}
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
                    {canEdit && !hasRealSource && (
                      <td>
                        <button
                          type="button"
                          className={styles.removeButton}
                          disabled={busy || state.columns.length <= 1}
                          title={state.columns.length <= 1 ? "El modelo necesita al menos una columna" : "Quitar columna"}
                          onClick={() => handleRemoveColumn(col.name)}
                        >
                          ×
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className={formStyles.hint}>El modelo no tiene ninguna columna todavía.</p>
          )}
          {canEdit && !hasRealSource && (
            <ColumnBuilderRow onAdd={handleAddColumn} disabled={busy} existingNames={state.columns.map((c) => c.name)} />
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
        description={
          hasRealSource
            ? `Se creará en Fabric un modelo semántico nuevo (DirectLake, una sola tabla) para "${itemName}", con sus columnas detectadas automáticamente a partir de la tabla real.`
            : `Se creará en Fabric un modelo semántico nuevo para "${itemName}" con las ${draftColumns.length} columna(s) indicadas, como diccionario de datos -- sin conexión a datos reales.`
        }
        confirmLabel="Crear"
        danger={false}
        busy={busy}
        onConfirm={handleCreate}
        onCancel={() => setConfirmCreateOpen(false)}
      />
    </div>
  );
}
