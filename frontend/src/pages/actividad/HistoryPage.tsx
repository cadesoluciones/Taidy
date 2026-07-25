import { useEffect, useState } from "react";

import { fetchHistory, type HistoryPage as HistoryPageData } from "../../api/history";
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
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    fetchHistory({ result: resultFilter, page, page_size: 20 })
      .then(setResult)
      .finally(() => setIsLoading(false));
  }, [resultFilter, page]);

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
