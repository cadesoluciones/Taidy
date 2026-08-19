import { useEffect, useState } from "react";

import type { SyncApplyDirection } from "../api/tasks";
import { fetchSyncMappings, type SyncMappingConfig } from "../api/syncMappings";
import { directionLabel, SYSTEM_LABELS } from "../utils/syncLabels";
import formStyles from "./Form.module.css";

interface SyncApplyFieldsProps {
  idPrefix: string;
  mapping: string;
  onMappingChange: (mapping: string) => void;
  direction: SyncApplyDirection;
  onDirectionChange: (direction: SyncApplyDirection) => void;
  confirmLargeBatch: boolean;
  onConfirmLargeBatchChange: (confirmLargeBatch: boolean) => void;
}

/** The "which mapeo, which direction" fields a `sync_apply` action needs --
 * shared by SchedulesPage (a scheduled sync) and WorkflowsPage (a sync as a
 * flow step), the same way both already share a `run_pipeline` fields
 * block. Unlike the manual "Sincronizar" button on Comparar, there's no one
 * watching a scheduled/flow-driven run to pick individual rows or click
 * through a large-batch confirmation dialog -- it always applies every
 * pending change in the chosen direction, and `confirmLargeBatch` here is
 * the standing answer to that dialog instead of a one-off click. */
export function SyncApplyFields({
  idPrefix,
  mapping,
  onMappingChange,
  direction,
  onDirectionChange,
  confirmLargeBatch,
  onConfirmLargeBatchChange,
}: SyncApplyFieldsProps) {
  const [mappings, setMappings] = useState<SyncMappingConfig[]>([]);

  useEffect(() => {
    fetchSyncMappings()
      .then((res) => setMappings(res.items))
      .catch(() => setMappings([]));
  }, []);

  useEffect(() => {
    if (!mapping && mappings[0]) {
      onMappingChange(mappings[0].name);
    }
    // Only auto-pick once the list arrives -- not on every mapping/onMappingChange change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mappings]);

  const selected = mappings.find((m) => m.name === mapping) ?? null;
  const sourceLabel = selected ? (SYSTEM_LABELS[selected.source.system] ?? selected.source.system) : "Origen";
  const targetLabel = selected ? (SYSTEM_LABELS[selected.target.system] ?? selected.target.system) : "Destino";

  return (
    <>
      <div className={formStyles.field}>
        <label htmlFor={`${idPrefix}_mapping`}>Mapeo de sincronización</label>
        {mappings.length === 0 ? (
          <p className={formStyles.hint}>
            No hay mapeos definidos todavía -- créalos en Sincronización → Mapeos.
          </p>
        ) : (
          <select id={`${idPrefix}_mapping`} value={mapping} onChange={(e) => onMappingChange(e.target.value)}>
            {mappings.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name}
              </option>
            ))}
          </select>
        )}
      </div>
      <div className={formStyles.field}>
        <label htmlFor={`${idPrefix}_direction`}>Dirección</label>
        <select
          id={`${idPrefix}_direction`}
          value={direction}
          onChange={(e) => onDirectionChange(e.target.value as SyncApplyDirection)}
        >
          <option value="to_target">{directionLabel("to_target", sourceLabel, targetLabel)}</option>
          <option value="to_source">{directionLabel("to_source", sourceLabel, targetLabel)}</option>
          <option value="both">{directionLabel("both", sourceLabel, targetLabel)}</option>
        </select>
        <p className={formStyles.hint}>Se aplican todos los cambios pendientes en esa dirección, sin seleccionar filas.</p>
      </div>
      <label className={formStyles.checkboxField}>
        <input
          type="checkbox"
          checked={confirmLargeBatch}
          onChange={(e) => onConfirmLargeBatchChange(e.target.checked)}
        />
        <span>Permitir lotes grandes (más de 50 cambios) sin confirmación manual</span>
      </label>
    </>
  );
}
