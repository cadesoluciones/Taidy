import { Pencil, Plus, Trash2, X } from "lucide-react";

import {
  createHubspotTable,
  deleteHubspotTable,
  fetchHubspotAvailableProperties,
  fetchHubspotTablesFull,
  updateHubspotTable,
  type HubspotTableConfig,
  type UpdateHubspotTableInput,
} from "../api/meta";
import { useTableManager } from "../hooks/useTableManager";
import { appendField } from "../utils/fields";
import { AvailablePropertiesPicker } from "./AvailablePropertiesPicker";
import { ConfirmDialog } from "./ConfirmDialog";
import formStyles from "./Form.module.css";
import styles from "./TableManager.module.css";

interface HubspotForm {
  name: string;
  objectType: string;
  fieldsRaw: string;
  description: string;
}

const EMPTY_FORM: HubspotForm = {
  name: "",
  objectType: "",
  fieldsRaw: "",
  description: "",
};

/** Admin-only: register, edit or remove a HubSpot CRM object type in
 * hubspot_tables.yaml directly from the web UI, instead of hand-editing the
 * file on the server -- the exact same file src/hubspot_client/config.py
 * reads for a real extraction run. Only `object_type` (the HubSpot CRM
 * object path segment, e.g. "contacts") and `fields` (the properties to
 * request) matter here -- HubSpot's full extraction has none of Factorial's
 * date_range/employee_filter/incremental concepts yet. */
export function HubspotTableManager() {
  const mgr = useTableManager<HubspotTableConfig, HubspotForm, UpdateHubspotTableInput>({
    fetchAll: fetchHubspotTablesFull,
    create: createHubspotTable,
    update: updateHubspotTable,
    remove: deleteHubspotTable,
    emptyForm: EMPTY_FORM,
    itemToForm: (t) => ({
      name: t.name,
      objectType: t.object_type,
      fieldsRaw: t.fields.join(", "),
      description: t.description,
    }),
    formToInput: (f) => {
      const fields = f.fieldsRaw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      if (!f.name.trim()) {
        return { error: "El objeto necesita un nombre." };
      }
      if (!f.objectType.trim()) {
        return { error: "Indica el tipo de objeto de HubSpot (ej. contacts, companies, deals)." };
      }
      if (fields.length === 0) {
        return { error: "Indica al menos una propiedad a extraer (separadas por comas)." };
      }
      return {
        input: {
          name: f.name.trim(),
          object_type: f.objectType.trim(),
          fields,
          description: f.description,
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
            <label htmlFor="new_hs_table_name">Nombre</label>
            <input
              id="new_hs_table_name"
              type="text"
              value={mgr.form.name}
              onChange={(e) => mgr.setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="hubspot_tickets"
            />
            {mgr.editingName && (
              <p className={formStyles.hint}>
                Cambiar el nombre no actualiza tareas programadas que ya lo seleccionen por su nombre anterior.
              </p>
            )}
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_hs_table_object_type">Tipo de objeto de HubSpot</label>
            <input
              id="new_hs_table_object_type"
              type="text"
              value={mgr.form.objectType}
              onChange={(e) => mgr.setForm((f) => ({ ...f, objectType: e.target.value }))}
              placeholder="tickets"
            />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_hs_table_fields">Propiedades a conservar (separadas por comas)</label>
            <input
              id="new_hs_table_fields"
              type="text"
              value={mgr.form.fieldsRaw}
              onChange={(e) => mgr.setForm((f) => ({ ...f, fieldsRaw: e.target.value }))}
              placeholder="hs_object_id, subject, hs_pipeline_stage"
            />
            <AvailablePropertiesPicker
              disabled={!mgr.form.objectType.trim()}
              disabledHint="Escribe primero el tipo de objeto de HubSpot."
              showHiddenToggle
              fetchProperties={(includeHidden) => fetchHubspotAvailableProperties(mgr.form.objectType.trim(), includeHidden)}
              onPick={(name) => mgr.setForm((f) => ({ ...f, fieldsRaw: appendField(f.fieldsRaw, name) }))}
            />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="new_hs_table_desc">Descripción (opcional)</label>
            <input
              id="new_hs_table_desc"
              type="text"
              value={mgr.form.description}
              onChange={(e) => mgr.setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <button type="submit" className={formStyles.submit}>
            {mgr.editingName ? (
              "Guardar cambios"
            ) : (
              <>
                <Plus size={14} /> Añadir objeto
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
                  <span className={styles.badge}>{t.object_type}</span>
                </div>
                <div className={styles.itemActions}>
                  <button
                    type="button"
                    className={styles.editBtn}
                    aria-label={`Editar objeto ${t.name}`}
                    onClick={() => mgr.startEdit(t)}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    className={styles.deleteBtn}
                    aria-label={`Borrar objeto ${t.name}`}
                    onClick={() => mgr.setPendingDelete(t)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className={formStyles.hint}>Todavía no hay objetos de HubSpot registrados.</p>
        )}
      </div>

      <ConfirmDialog
        open={mgr.pendingDelete !== null}
        title="Borrar objeto"
        description={`Vas a borrar "${mgr.pendingDelete?.name}" de hubspot_tables.yaml. Cualquier tarea programada que lo seleccione explícitamente dejará de encontrarlo.`}
        confirmLabel="Borrar definitivamente"
        busy={mgr.isBusy}
        onConfirm={mgr.confirmDelete}
        onCancel={() => mgr.setPendingDelete(null)}
      />
    </div>
  );
}
