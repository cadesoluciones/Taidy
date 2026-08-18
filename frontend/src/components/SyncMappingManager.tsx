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
  type RowFilter,
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
  const [sourceFilterField, setSourceFilterField] = useState("");
  const [sourceFilterValue, setSourceFilterValue] = useState("");
  const [targetFilterField, setTargetFilterField] = useState("");
  const [targetFilterValue, setTargetFilterValue] = useState("");

  const [sourceTables, setSourceTables] = useState<string[]>([]);
  const [targetTables, setTargetTables] = useState<string[]>([]);
  const [sourceFields, setSourceFields] = useState<string[]>([]);
  const [targetFields, setTargetFields] = useState<string[]>([]);
  const [sourceFieldQuery, setSourceFieldQuery] = useState("");
  const [targetFieldQuery, setTargetFieldQuery] = useState("");

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
    setSourceFilterField("");
    setSourceFilterValue("");
    setTargetFilterField("");
    setTargetFilterValue("");
    setSourceFieldQuery("");
    setTargetFieldQuery("");
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
    setSourceFilterField(mapping.source_filter?.field ?? "");
    setSourceFilterValue(mapping.source_filter?.equals ?? "");
    setTargetFilterField(mapping.target_filter?.field ?? "");
    setTargetFilterValue(mapping.target_filter?.equals ?? "");
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
  // Not just `!!editingName` -- the name field is now editable during a
  // rename too, so a blanked-out name while editing must block submit just
  // like it does when creating.
  const hasName = !!name.trim();
  // A filter is optional, but half-filled (field without a value, or vice
  // versa) is never a valid state to save -- it would silently mean "no
  // filter" server-side, which isn't what a half-filled row usually means.
  const sourceFilterPartial = !!sourceFilterField !== !!sourceFilterValue.trim();
  const targetFilterPartial = !!targetFilterField !== !!targetFilterValue.trim();
  const canSubmit = hasTables && hasKey && hasDate && hasFields && hasName && !sourceFilterPartial && !targetFilterPartial;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (sourceFilterPartial || targetFilterPartial) {
      setError("El filtro necesita tanto el campo como el valor (o déjalo vacío del todo).");
      return;
    }
    if (!canSubmit) {
      setError("Completa lo que falte en la lista de arriba antes de guardar.");
      return;
    }

    const sourceFilter: RowFilter | null =
      sourceFilterField && sourceFilterValue.trim() ? { field: sourceFilterField, equals: sourceFilterValue.trim() } : null;
    const targetFilter: RowFilter | null =
      targetFilterField && targetFilterValue.trim() ? { field: targetFilterField, equals: targetFilterValue.trim() } : null;

    const input = {
      name: name.trim(),
      source: { system: sourceSystem, table: sourceTable },
      target: { system: targetSystem, table: targetTable },
      matching_key: matchingKey,
      date_field: dateField,
      fields: cleanFields,
      description,
      source_filter: sourceFilter,
      target_filter: targetFilter,
    };

    try {
      if (editingName) {
        const updated = await updateSyncMapping(editingName, input);
        setSuccess(`'${updated.name}' actualizado.`);
      } else {
        const created = await createSyncMapping(input);
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
  const visibleSourceFields = sourceFields.filter((f) => f.toLowerCase().includes(sourceFieldQuery.trim().toLowerCase()));
  const visibleTargetFields = targetFields.filter((f) => f.toLowerCase().includes(targetFieldQuery.trim().toLowerCase()));

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
              onChange={(e) => setName(e.target.value)}
              placeholder="bc_contact_a_hubspot_contacts"
            />
            {editingName && (
              <p className={formStyles.hint}>
                Cambiar el nombre no actualiza tareas programadas que ya lo seleccionen por su nombre anterior.
              </p>
            )}
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
                setSourceFilterField("");
                setSourceFilterValue("");
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
                setSourceFilterField("");
                setSourceFilterValue("");
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
                setTargetFilterField("");
                setTargetFilterValue("");
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
                setTargetFilterField("");
                setTargetFilterValue("");
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

            <div className={formStyles.field}>
              <label>Filtro (opcional)</label>
              <p className={formStyles.hint}>
                Solo incluye filas donde el campo valga exactamente ese texto -- útil cuando una tabla mezcla varios
                tipos de registro (ej. el campo "type" de Business Central vale "Person" o "Company", pero aquí solo
                quieres uno de los dos).
              </p>
              <div className={styles.keyRow}>
                <DropCell
                  value={sourceFilterField}
                  placeholder="Campo origen (opcional)"
                  side="source"
                  extraClassName={styles.dropCellKey}
                  onDropValue={(v) => setSourceFilterField(v)}
                />
                <span className={styles.keyArrow}>=</span>
                <input
                  type="text"
                  value={sourceFilterValue}
                  onChange={(e) => setSourceFilterValue(e.target.value)}
                  placeholder="Valor"
                  className={styles.filterValueInput}
                />
              </div>
              <div className={styles.keyRow} style={{ marginTop: "var(--space-2)" }}>
                <DropCell
                  value={targetFilterField}
                  placeholder="Campo destino (opcional)"
                  side="target"
                  extraClassName={styles.dropCellKey}
                  onDropValue={(v) => setTargetFilterField(v)}
                />
                <span className={styles.keyArrow}>=</span>
                <input
                  type="text"
                  value={targetFilterValue}
                  onChange={(e) => setTargetFilterValue(e.target.value)}
                  placeholder="Valor"
                  className={styles.filterValueInput}
                />
              </div>
            </div>

            <div className={styles.columns}>
              <div className={styles.fieldColumn}>
                <div className={styles.fieldColumnTitle}>Campos de {SYSTEM_LABELS[sourceSystem]}</div>
                <input
                  type="text"
                  className={styles.fieldSearch}
                  placeholder="Buscar campo…"
                  value={sourceFieldQuery}
                  onChange={(e) => setSourceFieldQuery(e.target.value)}
                />
                <div className={styles.fieldList}>
                  {visibleSourceFields.length === 0 && <p className={styles.emptyHint}>Sin campos disponibles.</p>}
                  {visibleSourceFields.map((f) => (
                    <FieldChip key={f} side="source" value={f} dimmed={usedSourceFields.has(f)} />
                  ))}
                </div>
              </div>
              <div className={styles.fieldColumn}>
                <div className={styles.fieldColumnTitle}>Campos de {SYSTEM_LABELS[targetSystem]}</div>
                <input
                  type="text"
                  className={styles.fieldSearch}
                  placeholder="Buscar campo…"
                  value={targetFieldQuery}
                  onChange={(e) => setTargetFieldQuery(e.target.value)}
                />
                <div className={styles.fieldList}>
                  {visibleTargetFields.length === 0 && <p className={styles.emptyHint}>Sin campos disponibles.</p>}
                  {visibleTargetFields.map((f) => (
                    <FieldChip key={f} side="target" value={f} dimmed={usedTargetFields.has(f)} />
                  ))}
                </div>
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
                {m.source_filter && (
                  <span className={tableStyles.badge}>
                    filtro origen: {m.source_filter.field}={m.source_filter.equals}
                  </span>
                )}
                {m.target_filter && (
                  <span className={tableStyles.badge}>
                    filtro destino: {m.target_filter.field}={m.target_filter.equals}
                  </span>
                )}
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
