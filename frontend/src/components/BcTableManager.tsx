import { useEffect, useState } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";

import { ApiError } from "../api/client";
import {
  createBcTable,
  deleteBcTable,
  fetchBcTablesFull,
  updateBcTable,
  type BcTableConfig,
} from "../api/meta";
import { ConfirmDialog } from "./ConfirmDialog";
import formStyles from "./Form.module.css";
import styles from "./TableManager.module.css";

const EMPTY_FORM = { url: "", description: "", incremental: false };

/** Admin-only: register, edit or remove a Business Central table in
 * tables.yaml directly from the web UI, instead of hand-editing the file
 * on the server -- the exact same file src/bc_client/config.py reads for
 * a real extraction run. */
export function BcTableManager() {
  const [tables, setTables] = useState<BcTableConfig[]>([]);
  const [pendingDelete, setPendingDelete] = useState<BcTableConfig | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const [editingName, setEditingName] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState(EMPTY_FORM.url);
  const [description, setDescription] = useState(EMPTY_FORM.description);
  const [incremental, setIncremental] = useState(EMPTY_FORM.incremental);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function reload() {
    setTables((await fetchBcTablesFull()).items);
  }

  useEffect(() => {
    void reload();
  }, []);

  function startEdit(t: BcTableConfig) {
    setEditingName(t.name);
    setName(t.name);
    setUrl(t.url);
    setDescription(t.description);
    setIncremental(t.incremental);
    setError(null);
    setSuccess(null);
  }

  function cancelEdit() {
    setEditingName(null);
    setName("");
    setUrl(EMPTY_FORM.url);
    setDescription(EMPTY_FORM.description);
    setIncremental(EMPTY_FORM.incremental);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      if (editingName) {
        await updateBcTable(editingName, { url, description, incremental });
        setSuccess(`Tabla '${editingName}' actualizada.`);
        cancelEdit();
      } else {
        await createBcTable({ name, url, description, incremental });
        setSuccess(`Tabla '${name}' añadida.`);
        setName("");
        setUrl(EMPTY_FORM.url);
        setDescription(EMPTY_FORM.description);
        setIncremental(EMPTY_FORM.incremental);
      }
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar la tabla.");
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setIsBusy(true);
    try {
      await deleteBcTable(pendingDelete.name);
      if (editingName === pendingDelete.name) cancelEdit();
      await reload();
    } finally {
      setIsBusy(false);
      setPendingDelete(null);
    }
  }

  return (
    <div className={styles.layout}>
      <div className={styles.formPanel}>
        {success && <div className={formStyles.successBanner}>{success}</div>}
        {error && <div className={formStyles.errorBanner}>{error}</div>}
        <form className={formStyles.card} onSubmit={handleSubmit}>
          {editingName && (
            <div className={styles.editingBanner}>
              Editando <strong>{editingName}</strong>
              <button type="button" className={styles.cancelEditBtn} onClick={cancelEdit} aria-label="Cancelar edición">
                <X size={13} />
              </button>
            </div>
          )}
          <div className={formStyles.field}>
            <label htmlFor="new_bc_table_name">Nombre de la tabla</label>
            <input
              id="new_bc_table_name"
              type="text"
              value={name}
              disabled={!!editingName}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_bc_table_url">URL de OData</label>
            <input id="new_bc_table_url" type="text" value={url} onChange={(e) => setUrl(e.target.value)} />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_bc_table_desc">Descripción (opcional)</label>
            <input
              id="new_bc_table_desc"
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <label className={formStyles.checkboxField}>
            <input type="checkbox" checked={incremental} onChange={(e) => setIncremental(e.target.checked)} />
            <span>Soporta extracción incremental (watermark)</span>
          </label>
          <button type="submit" className={formStyles.submit}>
            {editingName ? "Guardar cambios" : (
              <>
                <Plus size={14} /> Añadir tabla
              </>
            )}
          </button>
        </form>
      </div>

      <div className={styles.listPanel}>
        {tables.length > 0 ? (
          <ul className={styles.list}>
            {tables.map((t) => (
              <li key={t.name} className={styles.listItem}>
                <div>
                  <strong>{t.name}</strong>
                  {t.description && <span className={styles.desc}> — {t.description}</span>}
                  {t.incremental && <span className={styles.badge}>incremental</span>}
                </div>
                <div className={styles.itemActions}>
                  <button
                    type="button"
                    className={styles.editBtn}
                    aria-label={`Editar tabla ${t.name}`}
                    onClick={() => startEdit(t)}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    className={styles.deleteBtn}
                    aria-label={`Borrar tabla ${t.name}`}
                    onClick={() => setPendingDelete(t)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className={formStyles.hint}>Todavía no hay tablas de Business Central registradas.</p>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Borrar tabla"
        description={`Vas a borrar la tabla "${pendingDelete?.name}" de tables.yaml. Cualquier tarea programada que la seleccione explícitamente dejará de encontrarla.`}
        confirmLabel="Borrar definitivamente"
        busy={isBusy}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
