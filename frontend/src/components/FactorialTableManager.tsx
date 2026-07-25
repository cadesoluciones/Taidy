import { useEffect, useState } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";

import { ApiError } from "../api/client";
import {
  createFactorialTable,
  deleteFactorialTable,
  fetchFactorialTablesFull,
  updateFactorialTable,
  type FactorialTableConfig,
} from "../api/meta";
import { ConfirmDialog } from "./ConfirmDialog";
import formStyles from "./Form.module.css";
import styles from "./TableManager.module.css";

const EMPTY_FORM = {
  path: "",
  fieldsRaw: "",
  description: "",
  dateRange: true,
  employeeFilter: true,
  incremental: false,
  overlapDays: "",
  chunkDays: "",
};

/** Admin-only: register, edit or remove a Factorial HR table in
 * factorial_tables.yaml directly from the web UI, instead of hand-editing
 * the file on the server -- the exact same file src/factorial_client/config.py
 * reads for a real extraction run. `fields` is required there too (the
 * API response fields to keep), so it's required here as well. */
export function FactorialTableManager() {
  const [tables, setTables] = useState<FactorialTableConfig[]>([]);
  const [pendingDelete, setPendingDelete] = useState<FactorialTableConfig | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const [editingName, setEditingName] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [path, setPath] = useState(EMPTY_FORM.path);
  const [fieldsRaw, setFieldsRaw] = useState(EMPTY_FORM.fieldsRaw);
  const [description, setDescription] = useState(EMPTY_FORM.description);
  const [dateRange, setDateRange] = useState(EMPTY_FORM.dateRange);
  const [employeeFilter, setEmployeeFilter] = useState(EMPTY_FORM.employeeFilter);
  const [incremental, setIncremental] = useState(EMPTY_FORM.incremental);
  const [overlapDays, setOverlapDays] = useState(EMPTY_FORM.overlapDays);
  const [chunkDays, setChunkDays] = useState(EMPTY_FORM.chunkDays);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function reload() {
    setTables((await fetchFactorialTablesFull()).items);
  }

  useEffect(() => {
    void reload();
  }, []);

  function startEdit(t: FactorialTableConfig) {
    setEditingName(t.name);
    setName(t.name);
    setPath(t.path);
    setFieldsRaw(t.fields.join(", "));
    setDescription(t.description);
    setDateRange(t.date_range);
    setEmployeeFilter(t.employee_filter);
    setIncremental(t.incremental);
    setOverlapDays(t.overlap_days != null ? String(t.overlap_days) : "");
    setChunkDays(t.chunk_days != null ? String(t.chunk_days) : "");
    setError(null);
    setSuccess(null);
  }

  function cancelEdit() {
    setEditingName(null);
    setName("");
    setPath(EMPTY_FORM.path);
    setFieldsRaw(EMPTY_FORM.fieldsRaw);
    setDescription(EMPTY_FORM.description);
    setDateRange(EMPTY_FORM.dateRange);
    setEmployeeFilter(EMPTY_FORM.employeeFilter);
    setIncremental(EMPTY_FORM.incremental);
    setOverlapDays(EMPTY_FORM.overlapDays);
    setChunkDays(EMPTY_FORM.chunkDays);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const fields = fieldsRaw
      .split(",")
      .map((f) => f.trim())
      .filter(Boolean);
    if (fields.length === 0) {
      setError("Indica al menos un campo que devuelve la API (separados por comas).");
      return;
    }
    const shared = {
      path,
      fields,
      description,
      date_range: dateRange,
      employee_filter: employeeFilter,
      incremental,
      overlap_days: overlapDays ? Number(overlapDays) : null,
      chunk_days: chunkDays ? Number(chunkDays) : null,
    };
    try {
      if (editingName) {
        await updateFactorialTable(editingName, shared);
        setSuccess(`Tabla '${editingName}' actualizada.`);
        cancelEdit();
      } else {
        await createFactorialTable({ name, ...shared });
        setSuccess(`Tabla '${name}' añadida.`);
        setName("");
        cancelEdit();
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
      await deleteFactorialTable(pendingDelete.name);
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
            <label htmlFor="new_fac_table_name">Nombre de la tabla</label>
            <input
              id="new_fac_table_name"
              type="text"
              value={name}
              disabled={!!editingName}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_fac_table_path">Ruta de la API (ej. resources/employees/employees)</label>
            <input id="new_fac_table_path" type="text" value={path} onChange={(e) => setPath(e.target.value)} />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_fac_table_fields">Campos a conservar (separados por comas)</label>
            <input
              id="new_fac_table_fields"
              type="text"
              value={fieldsRaw}
              onChange={(e) => setFieldsRaw(e.target.value)}
              placeholder="id, email, active"
            />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_fac_table_desc">Descripción (opcional)</label>
            <input
              id="new_fac_table_desc"
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className={formStyles.grid}>
            <div className={formStyles.field}>
              <label htmlFor="new_fac_table_overlap">Días de solapamiento (opcional)</label>
              <input
                id="new_fac_table_overlap"
                type="number"
                min={0}
                value={overlapDays}
                onChange={(e) => setOverlapDays(e.target.value)}
              />
            </div>
            <div className={formStyles.field}>
              <label htmlFor="new_fac_table_chunk">Ventana de días (opcional)</label>
              <input
                id="new_fac_table_chunk"
                type="number"
                min={1}
                value={chunkDays}
                onChange={(e) => setChunkDays(e.target.value)}
              />
            </div>
          </div>
          <label className={formStyles.checkboxField}>
            <input type="checkbox" checked={dateRange} onChange={(e) => setDateRange(e.target.checked)} />
            <span>Envía 'Desde'/'Hasta' a la API</span>
          </label>
          <label className={formStyles.checkboxField}>
            <input type="checkbox" checked={employeeFilter} onChange={(e) => setEmployeeFilter(e.target.checked)} />
            <span>Admite filtrar por empleados</span>
          </label>
          <label className={formStyles.checkboxField}>
            <input type="checkbox" checked={incremental} onChange={(e) => setIncremental(e.target.checked)} />
            <span>Soporta extracción incremental (checkpoint)</span>
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
          <p className={formStyles.hint}>Todavía no hay tablas de Factorial registradas.</p>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Borrar tabla"
        description={`Vas a borrar la tabla "${pendingDelete?.name}" de factorial_tables.yaml. Cualquier tarea programada que la seleccione explícitamente dejará de encontrarla.`}
        confirmLabel="Borrar definitivamente"
        busy={isBusy}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
