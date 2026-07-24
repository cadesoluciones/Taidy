import { useEffect, useState } from "react";

import { fetchHistory, type HistoryEntry, type HistoryPage as HistoryPageData } from "../../api/history";
import styles from "./HistoryPage.module.css";

export function HistoryPage() {
  const [result, setResult] = useState<HistoryPageData | null>(null);
  const [resultFilter, setResultFilter] = useState<"all" | "ok" | "error" | "stopped">("all");
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    fetchHistory({ result: resultFilter, page, page_size: 20 })
      .then(setResult)
      .finally(() => setIsLoading(false));
  }, [resultFilter, page]);

  function icon(entry: HistoryEntry): string {
    if (entry.ok) return "✅";
    if (entry.status === "stopped") return "⏹️";
    return "❌";
  }

  return (
    <section>
      <h1>Historial de ejecuciones</h1>
      <div className={styles.filters}>
        <div className={styles.field}>
          <label htmlFor="result">Resultado</label>
          <select
            id="result"
            value={resultFilter}
            onChange={(e) => {
              setPage(1);
              setResultFilter(e.target.value as "all" | "ok" | "error" | "stopped");
            }}
          >
            <option value="all">Todos</option>
            <option value="ok">Correcto</option>
            <option value="error">Error</option>
            <option value="stopped">Detenida</option>
          </select>
        </div>
      </div>

      {result && (
        <p>
          Mostrando {result.total_matching} de {result.total_available} ejecuciones.
        </p>
      )}

      {!isLoading && result?.items.length === 0 && <p>Ningún resultado con los filtros actuales.</p>}

      {result?.items.map((entry, i) => (
        <div className={styles.entry} key={`${entry.finished_at}-${i}`}>
          <div className={styles.entryHead}>
            <span>{icon(entry)}</span>
            <strong>{entry.action}</strong>
            <span>— {entry.source} —</span>
            <span>{entry.finished_at}</span>
            {entry.duration_seconds !== null && <span>· {entry.duration_seconds}s</span>}
          </div>
          <div className={styles.entryMessage}>{entry.message}</div>
          {entry.log && (
            <details className={styles.logDetails}>
              <summary>Ver log</summary>
              <pre className={styles.log}>{entry.log}</pre>
            </details>
          )}
        </div>
      ))}

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
