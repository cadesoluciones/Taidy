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
import formStyles from "../../components/Form.module.css";
import styles from "./Sincronizacion.module.css";

const SYSTEM_LABELS: Record<string, string> = {
  business_central: "Business Central",
  factorial: "Factorial HR",
  hubspot: "HubSpot CRM",
};

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

function ActionTable({ rows }: { rows: RecordAction[] }) {
  if (rows.length === 0) return <p className={formStyles.hint}>Nada en esta categoría.</p>;
  return (
    <div className={styles.detailTableWrap}>
      <table className={styles.detailTable}>
        <thead>
          <tr>
            <th>Clave</th>
            <th>Fecha origen</th>
            <th>Fecha destino</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td>{r.key}</td>
              <td>{formatDate(r.source_date)}</td>
              <td>{formatDate(r.target_date)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SkippedTable({ rows }: { rows: SkippedRecord[] }) {
  if (rows.length === 0) return <p className={formStyles.hint}>Nada en esta categoría.</p>;
  return (
    <div className={styles.detailTableWrap}>
      <table className={styles.detailTable}>
        <thead>
          <tr>
            <th>Sistema</th>
            <th>Motivo</th>
            <th>Clave</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.system}-${r.key}-${i}`}>
              <td>{r.system === "source" ? "Origen" : "Destino"}</td>
              <td>{SKIP_REASON_LABELS[r.reason] ?? r.reason}</td>
              <td>{r.key || "(vacía)"}</td>
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

  return (
    <section>
      <h1>Comparar</h1>
      <p>
        Elige un mapeo ya definido en Sincronización → Mapeos y pulsa "Comparar" para ver, sin cambiar nada
        todavía, qué se crearía, qué se actualizaría en cada dirección y qué se saltaría por tener la clave mal.
      </p>

      {error && <div className={formStyles.errorBanner}>{error}</div>}

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
              <div className={styles.statTileLabel}>Nuevos en destino</div>
            </div>
            <div className={styles.statTile}>
              <div className={styles.statTileCount}>{report.create_in_source.length}</div>
              <div className={styles.statTileLabel}>Nuevos en origen</div>
            </div>
            <div className={styles.statTile}>
              <div className={styles.statTileCount}>{report.update_target.length}</div>
              <div className={styles.statTileLabel}>Actualizaciones → destino</div>
            </div>
            <div className={styles.statTile}>
              <div className={styles.statTileCount}>{report.update_source.length}</div>
              <div className={styles.statTileLabel}>Actualizaciones → origen</div>
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

          <details className={styles.category} open={report.create_in_target.length > 0}>
            <summary className={styles.categorySummary}>
              Nuevos en destino ({report.create_in_target.length})
            </summary>
            <ActionTable rows={report.create_in_target} />
          </details>
          <details className={styles.category} open={report.create_in_source.length > 0}>
            <summary className={styles.categorySummary}>
              Nuevos en origen ({report.create_in_source.length})
            </summary>
            <ActionTable rows={report.create_in_source} />
          </details>
          <details className={styles.category} open={report.update_target.length > 0}>
            <summary className={styles.categorySummary}>
              Actualizaciones hacia destino ({report.update_target.length})
            </summary>
            <ActionTable rows={report.update_target} />
          </details>
          <details className={styles.category} open={report.update_source.length > 0}>
            <summary className={styles.categorySummary}>
              Actualizaciones hacia origen ({report.update_source.length})
            </summary>
            <ActionTable rows={report.update_source} />
          </details>
          <details className={styles.category}>
            <summary className={styles.categorySummary}>Saltados por clave ({report.skipped.length})</summary>
            <SkippedTable rows={report.skipped} />
          </details>
          <details className={styles.category}>
            <summary className={styles.categorySummary}>Sin cambios ({report.unchanged.length})</summary>
            <ActionTable rows={report.unchanged} />
          </details>
        </>
      )}
    </section>
  );
}
