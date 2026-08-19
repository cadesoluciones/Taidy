import { Pencil, Plus, Trash2, X } from "lucide-react";

import {
  createFactorialTable,
  deleteFactorialTable,
  fetchFactorialAvailableFields,
  fetchFactorialAvailableTables,
  fetchFactorialTablesFull,
  updateFactorialTable,
  type FactorialTableConfig,
  type UpdateFactorialTableInput,
} from "../api/meta";
import { useTableManager } from "../hooks/useTableManager";
import { appendField } from "../utils/fields";
import { AvailablePropertiesPicker } from "./AvailablePropertiesPicker";
import { ConfirmDialog } from "./ConfirmDialog";
import formStyles from "./Form.module.css";
import styles from "./TableManager.module.css";

interface FactorialForm {
  name: string;
  path: string;
  fieldsRaw: string;
  description: string;
  dateRange: boolean;
  employeeFilter: boolean;
  incremental: boolean;
  overlapDays: string;
  chunkDays: string;
}

const EMPTY_FORM: FactorialForm = {
  name: "",
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
  const mgr = useTableManager<FactorialTableConfig, FactorialForm, UpdateFactorialTableInput>({
    fetchAll: fetchFactorialTablesFull,
    create: createFactorialTable,
    update: updateFactorialTable,
    remove: deleteFactorialTable,
    emptyForm: EMPTY_FORM,
    itemToForm: (t) => ({
      name: t.name,
      path: t.path,
      fieldsRaw: t.fields.join(", "),
      description: t.description,
      dateRange: t.date_range,
      employeeFilter: t.employee_filter,
      incremental: t.incremental,
      overlapDays: t.overlap_days != null ? String(t.overlap_days) : "",
      chunkDays: t.chunk_days != null ? String(t.chunk_days) : "",
    }),
    formToInput: (f) => {
      const fields = f.fieldsRaw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      if (!f.name.trim()) {
        return { error: "La tabla necesita un nombre." };
      }
      if (fields.length === 0) {
        return { error: "Indica al menos un campo que devuelve la API (separados por comas)." };
      }
      return {
        input: {
          name: f.name.trim(),
          path: f.path,
          fields,
          description: f.description,
          date_range: f.dateRange,
          employee_filter: f.employeeFilter,
          incremental: f.incremental,
          overlap_days: f.overlapDays ? Number(f.overlapDays) : null,
          chunk_days: f.chunkDays ? Number(f.chunkDays) : null,
        },
      };
    },
  });

  return (
    <div className={styles.layout}>
      <div className={styles.formPanel}>
        {mgr.success && <div className={formStyles.successBanner}>{mgr.success}</div>}
        {mgr.error && <div className={formStyles.errorBanner}>{mgr.error}</div>}
        <form
          className={formStyles.card}
          onSubmit={(e) => {
            e.preventDefault();
            void mgr.submit();
          }}
        >
          {mgr.editingName && (
            <div className={styles.editingBanner}>
              Editando <strong>{mgr.editingName}</strong>
              <button
                type="button"
                className={styles.cancelEditBtn}
                onClick={mgr.cancelEdit}
                aria-label="Cancelar edición"
              >
                <X size={13} />
              </button>
            </div>
          )}
          <div className={formStyles.field}>
            <label htmlFor="new_fac_table_name">Nombre de la tabla</label>
            <input
              id="new_fac_table_name"
              type="text"
              value={mgr.form.name}
              onChange={(e) => mgr.setForm((f) => ({ ...f, name: e.target.value }))}
            />
            {mgr.editingName && (
              <p className={formStyles.hint}>
                Cambiar el nombre no actualiza tareas programadas que ya la seleccionen por su nombre anterior.
              </p>
            )}
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_fac_table_path">Ruta de la API (ej. resources/employees/employees)</label>
            <input
              id="new_fac_table_path"
              type="text"
              value={mgr.form.path}
              onChange={(e) => mgr.setForm((f) => ({ ...f, path: e.target.value }))}
            />
            <AvailablePropertiesPicker
              buttonLabel="Ver tablas disponibles"
              fetchProperties={() => fetchFactorialAvailableTables()}
              onPick={(name) => mgr.setForm((f) => ({ ...f, path: name }))}
            />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_fac_table_fields">Campos a conservar (separados por comas)</label>
            <input
              id="new_fac_table_fields"
              type="text"
              value={mgr.form.fieldsRaw}
              onChange={(e) => mgr.setForm((f) => ({ ...f, fieldsRaw: e.target.value }))}
              placeholder="id, email, active"
            />
            <AvailablePropertiesPicker
              disabled={!mgr.form.path.trim()}
              disabledHint="Escribe primero la ruta de la API de Factorial."
              fetchProperties={() => fetchFactorialAvailableFields(mgr.form.path.trim(), mgr.form.dateRange)}
              onPick={(name) => mgr.setForm((f) => ({ ...f, fieldsRaw: appendField(f.fieldsRaw, name) }))}
            />
            <p className={formStyles.hint}>
              Factorial no tiene un catálogo de campos -- esto muestra los campos vistos en una muestra reciente de
              datos reales, así que puede no incluir campos poco comunes.
            </p>
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_fac_table_desc">Descripción (opcional)</label>
            <input
              id="new_fac_table_desc"
              type="text"
              value={mgr.form.description}
              onChange={(e) => mgr.setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className={formStyles.grid}>
            <div className={formStyles.field}>
              <label htmlFor="new_fac_table_overlap">Días de solapamiento (opcional)</label>
              <input
                id="new_fac_table_overlap"
                type="number"
                min={0}
                value={mgr.form.overlapDays}
                onChange={(e) => mgr.setForm((f) => ({ ...f, overlapDays: e.target.value }))}
              />
            </div>
            <div className={formStyles.field}>
              <label htmlFor="new_fac_table_chunk">Ventana de días (opcional)</label>
              <input
                id="new_fac_table_chunk"
                type="number"
                min={1}
                value={mgr.form.chunkDays}
                onChange={(e) => mgr.setForm((f) => ({ ...f, chunkDays: e.target.value }))}
              />
            </div>
          </div>
          <label className={formStyles.checkboxField}>
            <input
              type="checkbox"
              checked={mgr.form.dateRange}
              onChange={(e) => mgr.setForm((f) => ({ ...f, dateRange: e.target.checked }))}
            />
            <span>Envía 'Desde'/'Hasta' a la API</span>
          </label>
          <label className={formStyles.checkboxField}>
            <input
              type="checkbox"
              checked={mgr.form.employeeFilter}
              onChange={(e) => mgr.setForm((f) => ({ ...f, employeeFilter: e.target.checked }))}
            />
            <span>Admite filtrar por empleados</span>
          </label>
          <label className={formStyles.checkboxField}>
            <input
              type="checkbox"
              checked={mgr.form.incremental}
              onChange={(e) => mgr.setForm((f) => ({ ...f, incremental: e.target.checked }))}
            />
            <span>Soporta extracción incremental (checkpoint)</span>
          </label>
          <button type="submit" className={formStyles.submit}>
            {mgr.editingName ? (
              "Guardar cambios"
            ) : (
              <>
                <Plus size={14} /> Añadir tabla
              </>
            )}
          </button>
        </form>
      </div>

      <div className={styles.listPanel}>
        {mgr.items.length > 0 ? (
          <ul className={styles.list}>
            {mgr.items.map((t) => (
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
                    onClick={() => mgr.startEdit(t)}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    className={styles.deleteBtn}
                    aria-label={`Borrar tabla ${t.name}`}
                    onClick={() => mgr.setPendingDelete(t)}
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
        open={mgr.pendingDelete !== null}
        title="Borrar tabla"
        description={`Vas a borrar la tabla "${mgr.pendingDelete?.name}" de factorial_tables.yaml. Cualquier tarea programada que la seleccione explícitamente dejará de encontrarla.`}
        confirmLabel="Borrar definitivamente"
        busy={mgr.isBusy}
        onConfirm={mgr.confirmDelete}
        onCancel={() => mgr.setPendingDelete(null)}
      />
    </div>
  );
}
