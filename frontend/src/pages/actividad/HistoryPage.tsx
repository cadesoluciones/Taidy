import { useEffect, useState } from "react";

import { fetchHistory, type HistoryFilters, type HistoryPage as HistoryPageData } from "../../api/history";
import { ACTION_LABELS } from "../../components/actionLabels";
import formStyles from "../../components/Form.module.css";
import { OutcomeIcon } from "../../components/OutcomeIcon";
import { Timeline, type TimelineItem } from "../../components/Timeline";
import styles from "./HistoryPage.module.css";

function toneFor(status: string): "success" | "danger" | "neutral" {
  if (status === "ok") return "success";
  if (status === "error") return "danger";
  return "neutral";
}

export function HistoryPage() {
  const [result, setResult] = useState<HistoryPageData | null>(null);
  const [resultFilter, setResultFilter] = useState<"all" | "ok" | "error" | "stopped">("all");
  const [actionFilter, setActionFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Guards against a stale, earlier-fired request resolving after a
    // later one and overwriting it with results for the wrong filters --
    // see AuditPage.tsx's identical fix for the full explanation.
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    const filters: HistoryFilters = { result: resultFilter, page, page_size: 20 };
    if (actionFilter) filters.action = [actionFilter];
    if (sourceFilter.trim()) filters.source = [sourceFilter.trim()];
    if (dateFrom) filters.date_from = dateFrom;
    if (dateTo) filters.date_to = dateTo;
    fetchHistory(filters)
      .then((res) => {
        if (!cancelled) setResult(res);
      })
      .catch(() => {
        if (!cancelled) setError("No se pudo cargar el historial. Reintentando…");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [resultFilter, actionFilter, sourceFilter, dateFrom, dateTo, page]);

  function resetPageAnd<T>(setter: (v: T) => void) {
    return (v: T) => {
      setPage(1);
      setter(v);
    };
  }

  return (
    <section>
      <h1>Historial de ejecuciones</h1>
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      <div className={styles.filters}>
        <div className={styles.field}>
          <label htmlFor="result">Resultado</label>
          <select id="result" value={resultFilter} onChange={(e) => resetPageAnd(setResultFilter)(e.target.value as "all" | "ok" | "error" | "stopped")}>
            <option value="all">Todos</option>
            <option value="ok">Correcto</option>
            <option value="error">Error</option>
            <option value="stopped">Detenida</option>
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="action">Acción</label>
          <select id="action" value={actionFilter} onChange={(e) => resetPageAnd(setActionFilter)(e.target.value)}>
            <option value="">Todas</option>
            {Object.entries(ACTION_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="source">Origen (usuario)</label>
          <input
            id="source"
            type="text"
            value={sourceFilter}
            onChange={(e) => resetPageAnd(setSourceFilter)(e.target.value)}
            placeholder="ej. admin"
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="date_from">Desde</label>
          <input id="date_from" type="date" value={dateFrom} onChange={(e) => resetPageAnd(setDateFrom)(e.target.value)} />
        </div>
        <div className={styles.field}>
          <label htmlFor="date_to">Hasta</label>
          <input id="date_to" type="date" value={dateTo} onChange={(e) => resetPageAnd(setDateTo)(e.target.value)} />
        </div>
      </div>

      {isLoading && !result && <p>Cargando…</p>}

      {result && (
        <p>
          Mostrando {result.total_matching} de {result.total_available} ejecuciones.
        </p>
      )}

      {result && (
        <Timeline
          emptyLabel="Ningún resultado con los filtros actuales."
          items={result.items.map((entry, i): TimelineItem => ({
            key: `${entry.finished_at}-${i}`,
            icon: <OutcomeIcon ok={entry.ok} status={entry.status} />,
            tone: toneFor(entry.status),
            title: (
              <>
                {entry.action} <span className={styles.entrySource}>— {entry.source}</span>
              </>
            ),
            timestamp:
              entry.finished_at + (entry.duration_seconds !== null ? ` · ${entry.duration_seconds}s` : ""),
            description: (
              <>
                {entry.message}
                {entry.log && (
                  <details className={styles.logDetails}>
                    <summary>Ver log</summary>
                    <pre className={styles.log}>{entry.log}</pre>
                  </details>
                )}
              </>
            ),
          }))}
        />
      )}

      {result && result.total_pages > 1 && (
        <div className={styles.pagination}>
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Anterior
          </button>
          <span>
            Página {result.page} de {result.total_pages}
          </span>
          <button type="button" disabled={page >= result.total_pages} onClick={() => setPage((p) => p + 1)}>
            Siguiente
          </button>
        </div>
      )}
    </section>
  );
}
