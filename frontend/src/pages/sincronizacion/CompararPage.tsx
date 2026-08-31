import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import {
  compareSyncMapping,
  fetchSyncMappings,
  type ComparisonReport,
  type RecordAction,
  type SkippedRecord,
  type SyncMappingConfig,
} from "../../api/syncMappings";
import { syncApply, type SyncApplyDirection } from "../../api/tasks";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import formStyles from "../../components/Form.module.css";
import { PageHeader } from "../../components/PageHeader";
import { directionLabel, SYSTEM_LABELS } from "../../utils/syncLabels";
import styles from "./Sincronizacion.module.css";

// Mirrors src/sync_engine/apply.py's DEFAULT_THRESHOLD -- the server always
// re-validates this for real, this is only to decide client-side whether to
// show the extra confirmation dialog before calling the API.
const LARGE_BATCH_THRESHOLD = 50;

function countPendingActions(report: ComparisonReport, direction: SyncApplyDirection): number {
  let total = 0;
  if (direction === "to_target" || direction === "both") {
    total += report.create_in_target.length + report.update_target.length;
  }
  if (direction === "to_source" || direction === "both") {
    total += report.create_in_source.length + report.update_source.length;
  }
  return total;
}

/** Every key that's actually actionable (create/update) for the chosen
 * direction -- a key never appears in more than one category, so a plain
 * Set is enough. */
function relevantKeysForDirection(report: ComparisonReport, direction: SyncApplyDirection): Set<string> {
  const keys = new Set<string>();
  if (direction === "to_target" || direction === "both") {
    report.create_in_target.forEach((a) => keys.add(a.key));
    report.update_target.forEach((a) => keys.add(a.key));
  }
  if (direction === "to_source" || direction === "both") {
    report.create_in_source.forEach((a) => keys.add(a.key));
    report.update_source.forEach((a) => keys.add(a.key));
  }
  return keys;
}

const SKIP_REASON_LABELS: Record<string, string> = {
  empty_key: "clave vacía",
  duplicate_key: "clave duplicada",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

// BC's raw row always carries every exposed field regardless of what the
// mapping declares (no $select is ever applied -- see src/bc_client/api.py),
// and HubSpot's row always carries its own record id under "__hubspot_id"
// (attached unconditionally, see src/hubspot_client/api.py's _parse_data) --
// so both ids are always available here without any backend change, as long
// as we know which side of the mapping is which system.
function systemRowId(row: Record<string, unknown> | null | undefined, system: string): string {
  if (!row) return "—";
  if (system === "business_central") {
    const value = row["no"];
    return typeof value === "string" && value.trim() ? value : "—";
  }
  if (system === "hubspot") {
    const value = row["__hubspot_id"];
    return value != null && value !== "" ? String(value) : "—";
  }
  return "—";
}

const NAME_FIELDS = ["name", "firstname", "companyName", "dealname"];

function rowDisplayName(row: Record<string, unknown> | null | undefined): string {
  if (!row) return "—";
  for (const field of NAME_FIELDS) {
    const value = row[field];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "—";
}

interface RowSelection {
  selectedKeys: Set<string>;
  onToggle: (key: string) => void;
  onToggleAll: (keys: string[], checked: boolean) => void;
}

function ActionTable({
  rows,
  sourceSystem,
  targetSystem,
  sourceLabel,
  targetLabel,
  selection,
}: {
  rows: RecordAction[];
  sourceSystem: string;
  targetSystem: string;
  sourceLabel: string;
  targetLabel: string;
  selection?: RowSelection;
}) {
  if (rows.length === 0) return <p className={formStyles.hint}>Nada en esta categoría.</p>;
  const allKeys = rows.map((r) => r.key);
  const allSelected = selection ? allKeys.every((k) => selection.selectedKeys.has(k)) : false;
  return (
    <div className={styles.detailTableWrap}>
      <table className={styles.detailTable}>
        <thead>
          <tr>
            {selection && (
              <th>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(e) => selection.onToggleAll(allKeys, e.target.checked)}
                  aria-label="Seleccionar todos en esta categoría"
                />
              </th>
            )}
            <th>Clave</th>
            <th>ID en {sourceLabel}</th>
            <th>ID en {targetLabel}</th>
            <th>Fecha en {sourceLabel}</th>
            <th>Fecha en {targetLabel}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              {selection && (
                <td>
                  <input
                    type="checkbox"
                    checked={selection.selectedKeys.has(r.key)}
                    onChange={() => selection.onToggle(r.key)}
                    aria-label={`Seleccionar ${r.key}`}
                  />
                </td>
              )}
              <td>{r.key}</td>
              <td>{systemRowId(r.source_row, sourceSystem)}</td>
              <td>{systemRowId(r.target_row, targetSystem)}</td>
              <td>{formatDate(r.source_date)}</td>
              <td>{formatDate(r.target_date)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SkippedTable({
  rows,
  sourceSystem,
  targetSystem,
  sourceLabel,
  targetLabel,
}: {
  rows: SkippedRecord[];
  sourceSystem: string;
  targetSystem: string;
  sourceLabel: string;
  targetLabel: string;
}) {
  if (rows.length === 0) return <p className={formStyles.hint}>Nada en esta categoría.</p>;
  return (
    <div className={styles.detailTableWrap}>
      <table className={styles.detailTable}>
        <thead>
          <tr>
            <th>Sistema</th>
            <th>Motivo</th>
            <th>Clave</th>
            <th>ID</th>
            <th>Nombre</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.system}-${r.key}-${i}`}>
              <td>{r.system === "source" ? sourceLabel : targetLabel}</td>
              <td>{SKIP_REASON_LABELS[r.reason] ?? r.reason}</td>
              <td>{r.key || "(vacía)"}</td>
              <td>{systemRowId(r.row, r.system === "source" ? sourceSystem : targetSystem)}</td>
              <td>{rowDisplayName(r.row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CompararPage() {
  const [mappings, setMappings] = useState<SyncMappingConfig[]>([]);
  const [selectedName, setSelectedName] = useState("");
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [isComparing, setIsComparing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [direction, setDirection] = useState<SyncApplyDirection>("both");
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncSuccess, setSyncSuccess] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    fetchSyncMappings()
      .then((res) => {
        setMappings(res.items);
        setSelectedName((prev) => prev || res.items[0]?.name || "");
      })
      .catch(() => setMappings([]));
  }, []);

  const selected = mappings.find((m) => m.name === selectedName) ?? null;

  async function handleCompare() {
    if (!selectedName) return;
    setError(null);
    setReport(null);
    setSelectedKeys(new Set());
    setSyncSuccess(null);
    setSyncError(null);
    setIsComparing(true);
    try {
      const result = await compareSyncMapping(selectedName);
      setReport(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo comparar el mapeo.");
    } finally {
      setIsComparing(false);
    }
  }

  function toggleKey(key: string) {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleAllKeys(keys: string[], checked: boolean) {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      keys.forEach((k) => (checked ? next.add(k) : next.delete(k)));
      return next;
    });
  }

  function selectAllPendingForDirection() {
    if (!report) return;
    setSelectedKeys(relevantKeysForDirection(report, direction));
  }

  function clearSelection() {
    setSelectedKeys(new Set());
  }

  async function runSyncApply(confirmLargeBatch: boolean, keys: string[]) {
    if (!selectedName) return;
    setSyncError(null);
    setSyncSuccess(null);
    setIsSyncing(true);
    try {
      const task = await syncApply({
        mapping: selectedName,
        direction,
        keys,
        confirm_large_batch: confirmLargeBatch,
      });
      setSyncSuccess(`Sincronización iniciada (${task.id.slice(0, 8)}). Sigue el progreso en Tareas en curso.`);
      setReport(null); // the comparison is now stale -- force a fresh "Comparar" before syncing again
      setSelectedKeys(new Set());
    } catch (err) {
      setSyncError(err instanceof ApiError ? err.message : "No se pudo iniciar la sincronización.");
    } finally {
      setIsSyncing(false);
      setConfirmOpen(false);
    }
  }

  function handleSyncClick() {
    if (!report) return;
    const keys = [...selectedKeys].filter((k) => relevantForDirection.has(k));
    if (keys.length === 0) return;
    if (keys.length > LARGE_BATCH_THRESHOLD) {
      setConfirmOpen(true);
    } else {
      void runSyncApply(false, keys);
    }
  }

  const relevantForDirection = report ? relevantKeysForDirection(report, direction) : new Set<string>();
  const selectedForDirection = [...selectedKeys].filter((k) => relevantForDirection.has(k));
  const pendingForDirection = report ? countPendingActions(report, direction) : 0;

  const sourceSystem = selected?.source.system ?? "";
  const targetSystem = selected?.target.system ?? "";
  const sourceLabel = selected ? (SYSTEM_LABELS[selected.source.system] ?? selected.source.system) : "Origen";
  const targetLabel = selected ? (SYSTEM_LABELS[selected.target.system] ?? selected.target.system) : "Destino";

  return (
    <section>
      <PageHeader
        title="Comparar"
        description={
          <>
            Elige un mapeo ya definido en Sincronización → Mapeos y pulsa "Comparar" para ver, sin cambiar nada
            todavía, qué se crearía, qué se actualizaría en cada dirección y qué se saltaría por tener la clave mal.
          </>
        }
      />

      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {syncSuccess && <div className={formStyles.successBanner}>{syncSuccess}</div>}
      {syncError && <div className={formStyles.errorBanner}>{syncError}</div>}

      <div className={formStyles.card} style={{ maxWidth: "none" }}>
        <div className={formStyles.field}>
          <label htmlFor="sync_mapping_select">Mapeo</label>
          <select
            id="sync_mapping_select"
            value={selectedName}
            onChange={(e) => {
              setSelectedName(e.target.value);
              setReport(null);
              setError(null);
            }}
          >
            {mappings.length === 0 && <option value="">No hay mapeos definidos</option>}
            {mappings.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name}
              </option>
            ))}
          </select>
        </div>

        {selected && (
          <p className={styles.mappingSummary}>
            {SYSTEM_LABELS[selected.source.system] ?? selected.source.system} · {selected.source.table} →{" "}
            {SYSTEM_LABELS[selected.target.system] ?? selected.target.system} · {selected.target.table} — clave:{" "}
            {selected.matching_key.source}/{selected.matching_key.target} · fecha: {selected.date_field.source}/
            {selected.date_field.target}
          </p>
        )}

        <button
          type="button"
          className={formStyles.submit}
          disabled={!selectedName || isComparing}
          onClick={handleCompare}
        >
          {isComparing ? "Comparando…" : "Comparar"}
        </button>
      </div>

      {report && (
        <>
          <div className={styles.summaryGrid}>
            <div className={styles.statTile}>
              <div className={styles.statTileCount}>{report.create_in_target.length}</div>
              <div className={styles.statTileLabel}>Nuevos en {targetLabel}</div>
            </div>
            <div className={styles.statTile}>
              <div className={styles.statTileCount}>{report.create_in_source.length}</div>
              <div className={styles.statTileLabel}>Nuevos en {sourceLabel}</div>
            </div>
            <div className={styles.statTile}>
              <div className={styles.statTileCount}>{report.update_target.length}</div>
              <div className={styles.statTileLabel}>
                {sourceLabel} → {targetLabel}
              </div>
            </div>
            <div className={styles.statTile}>
              <div className={styles.statTileCount}>{report.update_source.length}</div>
              <div className={styles.statTileLabel}>
                {targetLabel} → {sourceLabel}
              </div>
            </div>
            <div className={styles.statTile}>
              <div className={styles.statTileCount}>{report.unchanged.length}</div>
              <div className={styles.statTileLabel}>Sin cambios</div>
            </div>
            <div className={styles.statTile}>
              <div className={styles.statTileCount}>{report.skipped.length}</div>
              <div className={styles.statTileLabel}>Saltados por clave</div>
            </div>
          </div>

          <div className={formStyles.card} style={{ maxWidth: "none" }}>
            <div className={formStyles.field}>
              <label htmlFor="sync_direction">Dirección a aplicar</label>
              <select
                id="sync_direction"
                value={direction}
                onChange={(e) => setDirection(e.target.value as SyncApplyDirection)}
              >
                <option value="to_target">{directionLabel("to_target", sourceLabel, targetLabel)}</option>
                <option value="to_source">{directionLabel("to_source", sourceLabel, targetLabel)}</option>
                <option value="both">{directionLabel("both", sourceLabel, targetLabel)}</option>
              </select>
            </div>
            <p className={formStyles.hint}>
              {selectedForDirection.length} seleccionada(s) de {pendingForDirection} acción(es) pendiente(s) en esta
              dirección
              {selectedForDirection.length > LARGE_BATCH_THRESHOLD &&
                " — pedirá confirmación adicional antes de escribir"}
              .
            </p>
            <div className={styles.selectionActions}>
              <button type="button" className={styles.linkButton} onClick={selectAllPendingForDirection}>
                Seleccionar todas
              </button>
              <button type="button" className={styles.linkButton} onClick={clearSelection}>
                Quitar selección
              </button>
            </div>
            <button
              type="button"
              className={formStyles.submit}
              disabled={isSyncing || selectedForDirection.length === 0}
              onClick={handleSyncClick}
            >
              {isSyncing ? "Sincronizando…" : `Sincronizar (${selectedForDirection.length})`}
            </button>
          </div>

          <details className={styles.category} open={report.create_in_target.length > 0}>
            <summary className={styles.categorySummary}>
              Nuevos en {targetLabel} ({report.create_in_target.length})
            </summary>
            <p className={formStyles.hint}>Existen en {sourceLabel} pero todavía no en {targetLabel}.</p>
            <ActionTable
              rows={report.create_in_target}
              sourceSystem={sourceSystem}
              targetSystem={targetSystem}
              sourceLabel={sourceLabel}
              targetLabel={targetLabel}
              selection={{ selectedKeys, onToggle: toggleKey, onToggleAll: toggleAllKeys }}
            />
          </details>
          <details className={styles.category} open={report.create_in_source.length > 0}>
            <summary className={styles.categorySummary}>
              Nuevos en {sourceLabel} ({report.create_in_source.length})
            </summary>
            <p className={formStyles.hint}>Existen en {targetLabel} pero todavía no en {sourceLabel}.</p>
            <ActionTable
              rows={report.create_in_source}
              sourceSystem={sourceSystem}
              targetSystem={targetSystem}
              sourceLabel={sourceLabel}
              targetLabel={targetLabel}
              selection={{ selectedKeys, onToggle: toggleKey, onToggleAll: toggleAllKeys }}
            />
          </details>
          <details className={styles.category} open={report.update_target.length > 0}>
            <summary className={styles.categorySummary}>
              {sourceLabel} → {targetLabel} ({report.update_target.length})
            </summary>
            <p className={formStyles.hint}>
              {sourceLabel} tiene la fecha más reciente — sus datos sobrescribirán {targetLabel}.
            </p>
            <ActionTable
              rows={report.update_target}
              sourceSystem={sourceSystem}
              targetSystem={targetSystem}
              sourceLabel={sourceLabel}
              targetLabel={targetLabel}
              selection={{ selectedKeys, onToggle: toggleKey, onToggleAll: toggleAllKeys }}
            />
          </details>
          <details className={styles.category} open={report.update_source.length > 0}>
            <summary className={styles.categorySummary}>
              {targetLabel} → {sourceLabel} ({report.update_source.length})
            </summary>
            <p className={formStyles.hint}>
              {targetLabel} tiene la fecha más reciente — sus datos sobrescribirán {sourceLabel}.
            </p>
            <ActionTable
              rows={report.update_source}
              sourceSystem={sourceSystem}
              targetSystem={targetSystem}
              sourceLabel={sourceLabel}
              targetLabel={targetLabel}
              selection={{ selectedKeys, onToggle: toggleKey, onToggleAll: toggleAllKeys }}
            />
          </details>
          <details className={styles.category}>
            <summary className={styles.categorySummary}>Saltados por clave ({report.skipped.length})</summary>
            <SkippedTable
              rows={report.skipped}
              sourceSystem={sourceSystem}
              targetSystem={targetSystem}
              sourceLabel={sourceLabel}
              targetLabel={targetLabel}
            />
          </details>
          <details className={styles.category}>
            <summary className={styles.categorySummary}>Sin cambios ({report.unchanged.length})</summary>
            <ActionTable
              rows={report.unchanged}
              sourceSystem={sourceSystem}
              targetSystem={targetSystem}
              sourceLabel={sourceLabel}
              targetLabel={targetLabel}
            />
          </details>
        </>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="Confirmar sincronización de gran volumen"
        description={`Esta ejecución tocaría ${selectedForDirection.length} registros seleccionados (${directionLabel(direction, sourceLabel, targetLabel)}), por encima del umbral de ${LARGE_BATCH_THRESHOLD}. ¿Seguro que quieres continuar?`}
        confirmLabel="Sí, sincronizar"
        busy={isSyncing}
        onConfirm={() => void runSyncApply(true, selectedForDirection)}
        onCancel={() => setConfirmOpen(false)}
      />
    </section>
  );
}
