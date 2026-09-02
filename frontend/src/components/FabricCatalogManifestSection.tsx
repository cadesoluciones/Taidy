import { useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import {
  fetchCatalogManifest,
  setCatalogManifest,
  type CatalogManifest,
  type CatalogManifestColumn,
} from "../api/fabricCatalog";
import styles from "./FabricCatalogManifestSection.module.css";
import formStyles from "./Form.module.css";

interface FabricCatalogManifestSectionProps {
  itemId: string;
  canEdit: boolean;
  /** True when the catalog item itself is "sin conexión" -- reading/
   * writing the manifest is always a live OneLake call, so there's nothing
   * useful this can do while that's the case. */
  offline?: boolean;
}

/** Edits a Lakehouse table's own catalog_manifests/<table>.yml -- the data
 * contract this workspace's `catalog_metadata` notebook reads to
 * (re)generate a matching catalog.<table> Delta table from (name/type/
 * description/example per real column). Confirmed live that notebook
 * overwrites catalog.<table> wholesale every time it runs, so this only
 * ever reads/writes the YAML manifest, never that Delta table -- editing
 * the table directly would just get silently discarded on the next run.
 * See webapp/fabric_catalog.py's get_catalog_manifest()/set_catalog_manifest(). */
export function FabricCatalogManifestSection({ itemId, canEdit, offline = false }: FabricCatalogManifestSectionProps) {
  const [manifest, setManifest] = useState<CatalogManifest | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [tableDescriptionDraft, setTableDescriptionDraft] = useState("");
  const [columnsDraft, setColumnsDraft] = useState<CatalogManifestColumn[]>([]);
  const [newColName, setNewColName] = useState("");

  // Same "ignore a slow response for a table that's no longer selected"
  // guard as FabricSemanticModelSection -- see its comment for why.
  const currentItemIdRef = useRef(itemId);
  currentItemIdRef.current = itemId;

  function applyManifest(result: CatalogManifest) {
    setManifest(result);
    setTableDescriptionDraft(result.table_description);
    setColumnsDraft(result.columns);
  }

  async function load() {
    const requestedItemId = itemId;
    setIsLoading(true);
    setError(null);
    try {
      const result = await fetchCatalogManifest(requestedItemId);
      if (currentItemIdRef.current !== requestedItemId) return;
      applyManifest(result);
    } catch (err) {
      if (currentItemIdRef.current !== requestedItemId) return;
      setError(err instanceof ApiError ? err.message : "No se pudo leer el manifiesto de catálogo.");
    } finally {
      if (currentItemIdRef.current === requestedItemId) setIsLoading(false);
    }
  }

  useEffect(() => {
    setManifest(null);
    setSaveSuccess(null);
    if (offline) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemId, offline]);

  async function handleSave() {
    const requestedItemId = itemId;
    setBusy(true);
    setError(null);
    setSaveSuccess(null);
    try {
      const result = await setCatalogManifest(requestedItemId, tableDescriptionDraft, columnsDraft);
      if (currentItemIdRef.current !== requestedItemId) return;
      applyManifest(result);
      setSaveSuccess("Guardado.");
    } catch (err) {
      if (currentItemIdRef.current !== requestedItemId) return;
      setError(err instanceof ApiError ? err.message : "No se pudo guardar el manifiesto.");
    } finally {
      if (currentItemIdRef.current === requestedItemId) setBusy(false);
    }
  }

  function updateColumn(index: number, patch: Partial<CatalogManifestColumn>) {
    setColumnsDraft((prev) => prev.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  }

  function removeColumn(index: number) {
    setColumnsDraft((prev) => prev.filter((_, i) => i !== index));
  }

  function addColumn() {
    const name = newColName.trim();
    if (!name || columnsDraft.some((c) => c.name.toLowerCase() === name.toLowerCase())) return;
    setColumnsDraft((prev) => [...prev, { name, data_type: "", description: "", example: "" }]);
    setNewColName("");
  }

  const isDirty =
    !!manifest &&
    (tableDescriptionDraft !== manifest.table_description || JSON.stringify(columnsDraft) !== JSON.stringify(manifest.columns));

  if (offline) {
    return (
      <p className={formStyles.hint}>
        Manifiesto de catálogo no disponible: este elemento está sin conexión. Vuelve a intentarlo cuando Fabric lo liste
        de nuevo.
      </p>
    );
  }

  if (isLoading) return <p className={formStyles.hint}>Cargando manifiesto de catálogo…</p>;

  return (
    <div className={styles.wrap}>
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {saveSuccess && <div className={formStyles.successBanner}>{saveSuccess}</div>}

      {manifest && !manifest.has_manifest && (
        <p className={styles.seedHint}>
          Esta tabla todavía no tiene un manifiesto de catálogo (catalog_manifests/*.yml) -- estas son sus columnas
          reales, rellena tipo/descripción/ejemplo y guarda para crearlo.
        </p>
      )}

      <div className={styles.tableDescField}>
        <label htmlFor="fc_manifest_table_description">Descripción de la tabla</label>
        <input
          id="fc_manifest_table_description"
          type="text"
          className={styles.tableDescInput}
          value={tableDescriptionDraft}
          onChange={(e) => setTableDescriptionDraft(e.target.value)}
          disabled={!canEdit}
        />
      </div>

      {columnsDraft.length > 0 ? (
        <table className={styles.columnsTable}>
          <thead>
            <tr>
              <th>Campo</th>
              <th>Tipo</th>
              <th>Descripción</th>
              <th>Ejemplo</th>
              {canEdit && <th />}
            </tr>
          </thead>
          <tbody>
            {columnsDraft.map((col, i) => (
              <tr key={`${col.name}-${i}`}>
                <td className={styles.nameCell}>
                  {canEdit ? (
                    <input
                      type="text"
                      className={styles.cellInput}
                      value={col.name}
                      onChange={(e) => updateColumn(i, { name: e.target.value })}
                    />
                  ) : (
                    col.name
                  )}
                </td>
                <td className={styles.typeCell}>
                  {canEdit ? (
                    <input
                      type="text"
                      className={styles.cellInput}
                      value={col.data_type}
                      onChange={(e) => updateColumn(i, { data_type: e.target.value })}
                    />
                  ) : (
                    col.data_type || <em>—</em>
                  )}
                </td>
                <td>
                  {canEdit ? (
                    <input
                      type="text"
                      className={styles.cellInput}
                      value={col.description}
                      onChange={(e) => updateColumn(i, { description: e.target.value })}
                    />
                  ) : (
                    col.description || <em>—</em>
                  )}
                </td>
                <td className={styles.exampleCell}>
                  {canEdit ? (
                    <input
                      type="text"
                      className={styles.cellInput}
                      value={col.example}
                      onChange={(e) => updateColumn(i, { example: e.target.value })}
                    />
                  ) : (
                    col.example || <em>—</em>
                  )}
                </td>
                {canEdit && (
                  <td>
                    <button
                      type="button"
                      className={styles.removeButton}
                      disabled={busy}
                      onClick={() => removeColumn(i)}
                      aria-label={`Quitar ${col.name}`}
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
        <p className={formStyles.hint}>Sin columnas todavía.</p>
      )}

      {canEdit && (
        <div className={styles.addRow}>
          <input
            type="text"
            className={styles.colInput}
            placeholder="Nombre de columna"
            value={newColName}
            disabled={busy}
            onChange={(e) => setNewColName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addColumn();
              }
            }}
          />
          <button type="button" className={styles.linkButton} disabled={busy || !newColName.trim()} onClick={addColumn}>
            + Añadir columna
          </button>
        </div>
      )}

      {canEdit && (
        <button
          type="button"
          className={`${formStyles.submit} no-print`}
          disabled={busy || !isDirty || columnsDraft.length === 0}
          onClick={() => void handleSave()}
        >
          {busy ? "Guardando…" : "Guardar"}
        </button>
      )}
    </div>
  );
}
