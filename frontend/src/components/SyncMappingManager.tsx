import { useEffect, useState } from "react";
import { ArrowRight, Check, GripVertical, Pencil, Trash2, X } from "lucide-react";

import {
  fetchBcTableFields,
  fetchBcTables,
  fetchFactorialTables,
  fetchFactorialTablesFull,
  fetchHubspotTables,
  fetchHubspotTablesFull,
} from "../api/meta";
import {
  createSyncMapping,
  deleteSyncMapping,
  fetchSyncMappings,
  updateSyncMapping,
  type FieldPair,
  type SyncMappingConfig,
} from "../api/syncMappings";
import { ApiError } from "../api/client";
import { ConfirmDialog } from "./ConfirmDialog";
import formStyles from "./Form.module.css";
import styles from "./SyncMappingManager.module.css";
import tableStyles from "./TableManager.module.css";

const SYSTEM_LABELS: Record<string, string> = {
  business_central: "Business Central",
  factorial: "Factorial HR",
  hubspot: "HubSpot CRM",
};

const SYSTEMS = Object.keys(SYSTEM_LABELS);

interface DragPayload {
  side: "source" | "target";
  value: string;
}

function readDragPayload(e: React.DragEvent): DragPayload | null {
  try {
    const raw = e.dataTransfer.getData("text/plain");
    const parsed = JSON.parse(raw);
    if (parsed && (parsed.side === "source" || parsed.side === "target") && typeof parsed.value === "string") {
      return parsed as DragPayload;
    }
  } catch {
    // Not our payload (e.g. a stray browser drag) -- ignore.
  }
  return null;
}

function FieldChip({ side, value, dimmed }: { side: "source" | "target"; value: string; dimmed: boolean }) {
  return (
    <div
      className={`${styles.chip} ${dimmed ? styles.chipUsed : ""}`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "copy";
        e.dataTransfer.setData("text/plain", JSON.stringify({ side, value } satisfies DragPayload));
      }}
    >
      <GripVertical size={12} aria-hidden="true" />
      {value}
    </div>
  );
}

function DropCell({
  value,
  placeholder,
  side,
  onDropValue,
  extraClassName,
}: {
  value: string;
  placeholder: string;
  side: "source" | "target";
  onDropValue: (value: string) => void;
  extraClassName?: string | undefined;
}) {
  return (
    <div
      className={`${styles.dropCell} ${value ? styles.dropCellFilled : ""} ${extraClassName ?? ""}`}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const payload = readDragPayload(e);
        if (!payload || payload.side !== side) return;
        onDropValue(payload.value);
      }}
    >
      {value || <span className={styles.dropPlaceholder}>{placeholder}</span>}
    </div>
  );
}

async function fieldsForTable(system: string, table: string): Promise<string[]> {
  if (!table) return [];
  if (system === "business_central") {
    return (await fetchBcTableFields(table)).items;
  }
  if (system === "factorial") {
    const found = (await fetchFactorialTablesFull()).items.find((t) => t.name === table);
    return found?.fields ?? [];
  }
  if (system === "hubspot") {
    const found = (await fetchHubspotTablesFull()).items.find((t) => t.name === table);
    return found?.fields ?? [];
  }
  return [];
}

async function tableNamesForSystem(system: string): Promise<string[]> {
  if (system === "business_central") return (await fetchBcTables()).items;
  if (system === "factorial") return (await fetchFactorialTables()).items;
  if (system === "hubspot") return (await fetchHubspotTables()).items;
  return [];
}

const EMPTY_KEY: FieldPair = { source: "", target: "" };

/** Admin-only: define which BC field goes to which HubSpot field (or, more
 * generally, any source table's field to any target table's field), plus
 * the matching key used to tell "this record already exists on the other
 * side" apart from "this one needs creating". Drag-and-drop rather than a
 * flat form because a field mapping is inherently a set of pairs, not a
 * handful of scalar inputs -- picking each side from two long dropdowns
 * per row would be far more tedious than dragging a chip once.
 *
 * This only edits sync_mappings.yaml -- no BC/HubSpot record is read or
 * written here. The engine that actually applies a mapping is a later
 * phase. */
export function SyncMappingManager() {
  const [mappings, setMappings] = useState<SyncMappingConfig[]>([]);
  const [editingName, setEditingName] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [sourceSystem, setSourceSystem] = useState("business_central");
  const [sourceTable, setSourceTable] = useState("");
  const [targetSystem, setTargetSystem] = useState("hubspot");
  const [targetTable, setTargetTable] = useState("");
  const [matchingKey, setMatchingKey] = useState<FieldPair>(EMPTY_KEY);
  const [dateField, setDateField] = useState<FieldPair>(EMPTY_KEY);
  const [fields, setFields] = useState<FieldPair[]>([]);

  const [sourceTables, setSourceTables] = useState<string[]>([]);
  const [targetTables, setTargetTables] = useState<string[]>([]);
  const [sourceFields, setSourceFields] = useState<string[]>([]);
  const [targetFields, setTargetFields] = useState<string[]>([]);

  const [pendingDelete, setPendingDelete] = useState<SyncMappingConfig | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function reload() {
    setMappings((await fetchSyncMappings()).items);
  }

  useEffect(() => {
    void reload();
  }, []);

  useEffect(() => {
    tableNamesForSystem(sourceSystem)
      .then(setSourceTables)
      .catch(() => setSourceTables([]));
  }, [sourceSystem]);

  useEffect(() => {
    tableNamesForSystem(targetSystem)
      .then(setTargetTables)
      .catch(() => setTargetTables([]));
  }, [targetSystem]);

  useEffect(() => {
    fieldsForTable(sourceSystem, sourceTable)
      .then(setSourceFields)
      .catch(() => setSourceFields([]));
  }, [sourceSystem, sourceTable]);

  useEffect(() => {
    fieldsForTable(targetSystem, targetTable)
      .then(setTargetFields)
      .catch(() => setTargetFields([]));
  }, [targetSystem, targetTable]);

  function resetDraft() {
    setEditingName(null);
    setName("");
    setDescription("");
    setSourceSystem("business_central");
    setSourceTable("");
    setTargetSystem("hubspot");
    setTargetTable("");
    setMatchingKey(EMPTY_KEY);
    setDateField(EMPTY_KEY);
    setFields([]);
  }

  function startEdit(mapping: SyncMappingConfig) {
    setError(null);
    setSuccess(null);
    setEditingName(mapping.name);
    setName(mapping.name);
    setDescription(mapping.description);
    setSourceSystem(mapping.source.system);
    setSourceTable(mapping.source.table);
    setTargetSystem(mapping.target.system);
    setTargetTable(mapping.target.table);
    setMatchingKey(mapping.matching_key);
    setDateField(mapping.date_field);
    setFields(mapping.fields);
  }

  function setFieldPairValue(rowIndex: number, side: "source" | "target", value: string) {
    setError(null);
    if (side === "source" && fields.some((f, i) => i !== rowIndex && f.source === value)) {
      setError(`El campo de origen "${value}" ya está mapeado en otra fila.`);
      return;
    }
    setFields((prev) => {
      const isTrailing = rowIndex === prev.length;
      const next = isTrailing ? [...prev, { ...EMPTY_KEY }] : [...prev];
      const current = next[rowIndex] ?? EMPTY_KEY;
      next[rowIndex] = side === "source" ? { ...current, source: value } : { ...current, target: value };
      return next;
    });
  }

  function removeFieldRow(rowIndex: number) {
    setFields((prev) => prev.filter((_, i) => i !== rowIndex));
  }

  const cleanFields = fields.filter((f) => f.source && f.target);
  const incompleteFieldRows = fields.length - cleanFields.length;
  const hasTables = !!sourceTable && !!targetTable;
  const hasKey = !!matchingKey.source && !!matchingKey.target;
  const hasDate = !!dateField.source && !!dateField.target;
  const hasFields = cleanFields.length > 0;
  const hasName = !!editingName || !!name.trim();
  const canSubmit = hasTables && hasKey && hasDate && hasFields && hasName;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!canSubmit) {
      setError("Completa lo que falte en la lista de arriba antes de guardar.");
      return;
    }

    const input = {
      source: { system: sourceSystem, table: sourceTable },
      target: { system: targetSystem, table: targetTable },
      matching_key: matchingKey,
      date_field: dateField,
      fields: cleanFields,
      description,
    };

    try {
      if (editingName) {
        await updateSyncMapping(editingName, input);
        setSuccess(`'${editingName}' actualizado.`);
      } else {
        const created = await createSyncMapping({ ...input, name: name.trim() });
        setSuccess(`'${created.name}' añadido.`);
      }
      resetDraft();
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar el mapeo.");
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setIsBusy(true);
    try {
      await deleteSyncMapping(pendingDelete.name);
      if (editingName === pendingDelete.name) resetDraft();
      await reload();
    } finally {
      setIsBusy(false);
      setPendingDelete(null);
    }
  }

  const usedSourceFields = new Set(fields.map((f) => f.source).filter(Boolean));
  const usedTargetFields = new Set(fields.map((f) => f.target).filter(Boolean));
  const displayRows = [...fields, { ...EMPTY_KEY }];

  return (
    <div>
      {success && <div className={formStyles.successBanner}>{success}</div>}
      {error && <div className={formStyles.errorBanner}>{error}</div>}

      <form className={`${formStyles.card} ${styles.wideCard}`} onSubmit={submit}>
        {editingName && (
          <div className={tableStyles.editingBanner}>
            Editando <strong>{editingName}</strong>
            <button type="button" className={tableStyles.cancelEditBtn} onClick={resetDraft} aria-label="Cancelar edición">
              <X size={13} />
            </button>
          </div>
        )}

        <div className={formStyles.grid}>
          <div className={formStyles.field}>
            <label htmlFor="sm_name">Nombre del mapeo</label>
            <input
              id="sm_name"
              type="text"
              value={name}
              disabled={!!editingName}
              onChange={(e) => setName(e.target.value)}
              placeholder="bc_contact_a_hubspot_contacts"
            />
          </div>
          <div className={formStyles.field}>
            <label htmlFor="sm_desc">Descripción (opcional)</label>
            <input id="sm_desc" type="text" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>

        <div className={formStyles.grid}>
          <div className={formStyles.field}>
            <label htmlFor="sm_source_system">Sistema origen</label>
            <select
              id="sm_source_system"
              value={sourceSystem}
              onChange={(e) => {
                setSourceSystem(e.target.value);
                setSourceTable("");
                setMatchingKey(EMPTY_KEY);
                setDateField(EMPTY_KEY);
                setFields([]);
              }}
            >
              {SYSTEMS.map((s) => (
                <option key={s} value={s}>
                  {SYSTEM_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          <div className={formStyles.field}>
            <label htmlFor="sm_source_table">Tabla origen</label>
            <select
              id="sm_source_table"
              value={sourceTable}
              onChange={(e) => {
                setSourceTable(e.target.value);
                setMatchingKey(EMPTY_KEY);
                setDateField(EMPTY_KEY);
                setFields([]);
              }}
            >
              <option value="">Selecciona una tabla…</option>
              {sourceTables.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className={formStyles.grid}>
          <div className={formStyles.field}>
            <label htmlFor="sm_target_system">Sistema destino</label>
            <select
              id="sm_target_system"
              value={targetSystem}
              onChange={(e) => {
                setTargetSystem(e.target.value);
                setTargetTable("");
                setMatchingKey(EMPTY_KEY);
                setDateField(EMPTY_KEY);
                setFields([]);
              }}
            >
              {SYSTEMS.map((s) => (
                <option key={s} value={s}>
                  {SYSTEM_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          <div className={formStyles.field}>
            <label htmlFor="sm_target_table">Tabla destino</label>
            <select
              id="sm_target_table"
              value={targetTable}
              onChange={(e) => {
                setTargetTable(e.target.value);
                setMatchingKey(EMPTY_KEY);
                setDateField(EMPTY_KEY);
                setFields([]);
              }}
            >
              <option value="">Selecciona una tabla…</option>
              {targetTables.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </div>

        {sourceSystem === "business_central" && sourceTable && sourceFields.length === 0 && (
          <p className={formStyles.hint}>
            '{sourceTable}' todavía no se ha extraído ni una vez, así que no hay campos que arrastrar. Lánzala una vez
            desde Ejecutar y vuelve aquí.
          </p>
        )}

        {sourceTable && targetTable && (
          <>
            <div className={formStyles.field}>
              <label>Clave de coincidencia</label>
              <p className={formStyles.hint}>
                El campo que identifica al mismo registro en ambos sistemas (ej. email). Arrastra un campo de cada
                columna.
              </p>
              <div className={styles.keyRow}>
                <DropCell
                  value={matchingKey.source}
                  placeholder="Campo origen"
                  side="source"
                  extraClassName={styles.dropCellKey}
                  onDropValue={(v) => setMatchingKey((prev) => ({ ...prev, source: v }))}
                />
                <ArrowRight size={16} className={styles.keyArrow} aria-hidden="true" />
                <DropCell
                  value={matchingKey.target}
                  placeholder="Campo destino"
                  side="target"
                  extraClassName={styles.dropCellKey}
                  onDropValue={(v) => setMatchingKey((prev) => ({ ...prev, target: v }))}
                />
              </div>
            </div>

            <div className={formStyles.field}>
              <label>Campo de fecha (para decidir quién gana un conflicto)</label>
              <p className={formStyles.hint}>
                El campo de "última modificación" de cada lado. Si un registro cambió en los dos sistemas, gana el
                que tenga la fecha más reciente.
              </p>
              <div className={styles.keyRow}>
                <DropCell
                  value={dateField.source}
                  placeholder="Campo origen"
                  side="source"
                  extraClassName={styles.dropCellKey}
                  onDropValue={(v) => setDateField((prev) => ({ ...prev, source: v }))}
                />
                <ArrowRight size={16} className={styles.keyArrow} aria-hidden="true" />
                <DropCell
                  value={dateField.target}
                  placeholder="Campo destino"
                  side="target"
                  extraClassName={styles.dropCellKey}
                  onDropValue={(v) => setDateField((prev) => ({ ...prev, target: v }))}
                />
              </div>
            </div>

            <div className={styles.columns}>
              <div className={styles.fieldColumn}>
                <div className={styles.fieldColumnTitle}>Campos de {SYSTEM_LABELS[sourceSystem]}</div>
                {sourceFields.length === 0 && <p className={styles.emptyHint}>Sin campos disponibles.</p>}
                {sourceFields.map((f) => (
                  <FieldChip key={f} side="source" value={f} dimmed={usedSourceFields.has(f)} />
                ))}
              </div>
              <div className={styles.fieldColumn}>
                <div className={styles.fieldColumnTitle}>Campos de {SYSTEM_LABELS[targetSystem]}</div>
                {targetFields.length === 0 && <p className={styles.emptyHint}>Sin campos disponibles.</p>}
                {targetFields.map((f) => (
                  <FieldChip key={f} side="target" value={f} dimmed={usedTargetFields.has(f)} />
                ))}
              </div>
              <div className={styles.fieldColumn}>
                <div className={styles.fieldColumnTitle}>Lienzo de mapeo</div>
                <div className={styles.canvas}>
                  {displayRows.map((row, i) => (
                    <div className={styles.canvasRow} key={i}>
                      <DropCell
                        value={row.source}
                        placeholder="Suelta un campo origen"
                        side="source"
                        onDropValue={(v) => setFieldPairValue(i, "source", v)}
                      />
                      <ArrowRight size={14} className={styles.rowArrow} aria-hidden="true" />
                      <DropCell
                        value={row.target}
                        placeholder="Suelta un campo destino"
                        side="target"
                        onDropValue={(v) => setFieldPairValue(i, "target", v)}
                      />
                      {i < fields.length ? (
                        <button
                          type="button"
                          className={styles.removeRowBtn}
                          aria-label="Quitar par de campos"
                          onClick={() => removeFieldRow(i)}
                        >
                          <Trash2 size={13} />
                        </button>
                      ) : (
                        <span />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {incompleteFieldRows > 0 && (
              <p className={formStyles.hint}>
                Hay {incompleteFieldRows} fila{incompleteFieldRows > 1 ? "s" : ""} en el lienzo con solo un lado
                relleno — para que cuente, suelta el campo que falta en <strong>esa misma fila</strong> (no en la
                fila vacía nueva que aparece debajo), o bórrala con la papelera si no la necesitas.
              </p>
            )}

            <ul className={styles.checklist}>
              <li className={`${styles.checklistItem} ${hasName ? styles.checklistOk : styles.checklistPending}`}>
                {hasName ? <Check size={14} /> : <span>○</span>} Nombre del mapeo
              </li>
              <li className={`${styles.checklistItem} ${hasKey ? styles.checklistOk : styles.checklistPending}`}>
                {hasKey ? <Check size={14} /> : <span>○</span>} Clave de coincidencia (origen y destino)
              </li>
              <li className={`${styles.checklistItem} ${hasDate ? styles.checklistOk : styles.checklistPending}`}>
                {hasDate ? <Check size={14} /> : <span>○</span>} Campo de fecha (origen y destino)
              </li>
              <li className={`${styles.checklistItem} ${hasFields ? styles.checklistOk : styles.checklistPending}`}>
                {hasFields ? <Check size={14} /> : <span>○</span>} Al menos un par de campos completo en el lienzo
              </li>
            </ul>
          </>
        )}

        <button type="submit" className={formStyles.submit} disabled={!canSubmit}>
          {editingName ? "Guardar cambios" : "Añadir mapeo"}
        </button>
      </form>

      {mappings.length > 0 && (
        <ul className={tableStyles.list} style={{ marginTop: "var(--space-4)" }}>
          {mappings.map((m) => (
            <li key={m.name} className={tableStyles.listItem}>
              <div>
                <strong>{m.name}</strong>
                {m.description && <span className={tableStyles.desc}> — {m.description}</span>}
                <span className={tableStyles.badge}>
                  {m.source.table} → {m.target.table}
                </span>
                <span className={tableStyles.badge}>clave: {m.matching_key.source}</span>
                <span className={tableStyles.badge}>fecha: {m.date_field.source}</span>
              </div>
              <div className={tableStyles.itemActions}>
                <button
                  type="button"
                  className={tableStyles.editBtn}
                  aria-label={`Editar mapeo ${m.name}`}
                  onClick={() => startEdit(m)}
                >
                  <Pencil size={14} />
                </button>
                <button
                  type="button"
                  className={tableStyles.deleteBtn}
                  aria-label={`Borrar mapeo ${m.name}`}
                  onClick={() => setPendingDelete(m)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {mappings.length === 0 && <p className={formStyles.hint}>Todavía no hay mapeos de sincronización definidos.</p>}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Borrar mapeo"
        description={`Vas a borrar el mapeo "${pendingDelete?.name}" de sync_mappings.yaml.`}
        confirmLabel="Borrar definitivamente"
        busy={isBusy}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
