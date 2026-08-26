import { Pencil, Plus, Trash2, X } from "lucide-react";

import {
  createBcTable,
  deleteBcTable,
  fetchBcAvailableTables,
  fetchBcTablesFull,
  updateBcTable,
  type BcTableConfig,
  type UpdateBcTableInput,
} from "../api/meta";
import { useTableManager } from "../hooks/useTableManager";
import { AvailablePropertiesPicker } from "./AvailablePropertiesPicker";
import { ConfirmDialog } from "./ConfirmDialog";
import formStyles from "./Form.module.css";
import styles from "./TableManager.module.css";

interface BcForm {
  name: string;
  url: string;
  description: string;
  incremental: boolean;
}

const EMPTY_FORM: BcForm = { name: "", url: "", description: "", incremental: false };

/** Unlike HubSpot/Factorial's pickers, BC's "name" (the short, scannable
 * entity id, e.g. "APIabc" or "Proyecto/recursos" for a Custom APIs entry)
 * is NOT the value that fills the form -- that's "label" instead (the
 * full, ready-to-save URL, too long to be the picker's bold primary text).
 * See BusinessCentralClient.list_available_tables. */
function suggestBcTableName(shortName: string): string {
  return `bc_${shortName.toLowerCase().replace(/\//g, "_")}`;
}

/** Admin-only: register, edit or remove a Business Central table in
 * tables.yaml directly from the web UI, instead of hand-editing the file on
 * the server -- the exact same file src/bc_client/config.py reads for a real
 * extraction run. Each table's `url` may carry a literal `{ENVIRONMENT}`
 * placeholder, substituted with BC_ENVIRONMENT at extraction time. */
export function BcTableManager() {
  const mgr = useTableManager<BcTableConfig, BcForm, UpdateBcTableInput>({
    fetchAll: fetchBcTablesFull,
    create: createBcTable,
    update: updateBcTable,
    remove: deleteBcTable,
    emptyForm: EMPTY_FORM,
    itemToForm: (t) => ({ name: t.name, url: t.url, description: t.description, incremental: t.incremental }),
    formToInput: (f) => {
      if (!f.name.trim()) return { error: "La tabla necesita un nombre." };
      return { input: { name: f.name.trim(), url: f.url, description: f.description, incremental: f.incremental } };
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
            <label htmlFor="new_bc_table_name">Nombre de la tabla</label>
            <input
              id="new_bc_table_name"
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
            <label htmlFor="new_bc_table_url">URL de OData</label>
            <input
              id="new_bc_table_url"
              type="text"
              value={mgr.form.url}
              onChange={(e) => mgr.setForm((f) => ({ ...f, url: e.target.value }))}
            />
            <AvailablePropertiesPicker
              buttonLabel="Ver tablas disponibles"
              fetchProperties={() => fetchBcAvailableTables()}
              onPick={(property) =>
                mgr.setForm((f) => ({
                  ...f,
                  url: property.label,
                  name: f.name.trim() ? f.name : suggestBcTableName(property.name),
                }))
              }
            />
            <p className={formStyles.hint}>
              Incluye tanto el API OData estándar como los grupos de "Custom APIs" (api/publisher/grupo/versión) ya
              usados por alguna tabla existente -- un grupo completamente nuevo aún necesita una primera tabla con la
              URL escrita a mano antes de aparecer aquí.
            </p>
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_bc_table_desc">Descripción (opcional)</label>
            <input
              id="new_bc_table_desc"
              type="text"
              value={mgr.form.description}
              onChange={(e) => mgr.setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <label className={formStyles.checkboxField}>
            <input
              type="checkbox"
              checked={mgr.form.incremental}
              onChange={(e) => mgr.setForm((f) => ({ ...f, incremental: e.target.checked }))}
            />
            <span>Soporta extracción incremental (watermark)</span>
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
          <p className={formStyles.hint}>Todavía no hay tablas de Business Central registradas.</p>
        )}
      </div>

      <ConfirmDialog
        open={mgr.pendingDelete !== null}
        title="Borrar tabla"
        description={`Vas a borrar la tabla "${mgr.pendingDelete?.name}" de tables.yaml. Cualquier tarea programada que la seleccione explícitamente dejará de encontrarla.`}
        confirmLabel="Borrar definitivamente"
        busy={mgr.isBusy}
        onConfirm={mgr.confirmDelete}
        onCancel={() => mgr.setPendingDelete(null)}
      />
    </div>
  );
}
