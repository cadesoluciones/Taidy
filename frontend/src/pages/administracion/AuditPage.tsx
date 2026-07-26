import { useEffect, useState } from "react";

import { fetchAudit, type AuditFilters, type AuditPage as AuditPageData } from "../../api/audit";
import formStyles from "../../components/Form.module.css";
import styles from "./AuditPage.module.css";

const EVENT_LABELS: Record<string, string> = {
  login: "Inicio de sesión",
  logout: "Cierre de sesión",
  password_change: "Cambio de contraseña",
  authorization: "Acceso denegado",
};

export function AuditPage() {
  const [data, setData] = useState<AuditPageData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventFilter, setEventFilter] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    // A later-changed filter's request can resolve before an earlier one
    // (or React 19 dev-mode's double-invoked first effect) -- without this
    // guard, whichever response happens to land last silently overwrites
    // the correct one, even though it no longer matches the selected
    // filters. Same pattern hooks/usePolling.ts already uses.
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    const filters: AuditFilters = {};
    if (eventFilter) filters.event = [eventFilter];
    if (outcomeFilter) filters.outcome = [outcomeFilter];
    if (userFilter.trim()) filters.user = [userFilter.trim()];
    if (dateFrom) filters.date_from = dateFrom;
    if (dateTo) filters.date_to = dateTo;
    fetchAudit(filters)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setError("No se pudo cargar la auditoría. Reintentando…");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [eventFilter, outcomeFilter, userFilter, dateFrom, dateTo]);

  return (
    <section>
      <h1>Auditoría de seguridad</h1>
      <p>Eventos de login, cierre de sesión, cambio de contraseña y accesos denegados. Nunca contiene tokens ni secretos.</p>

      {error && <div className={formStyles.errorBanner}>{error}</div>}

      <div className={styles.filters}>
        <div className={styles.field}>
          <label htmlFor="audit_event">Evento</label>
          <select id="audit_event" value={eventFilter} onChange={(e) => setEventFilter(e.target.value)}>
            <option value="">Todos</option>
            {Object.entries(EVENT_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="audit_outcome">Resultado</label>
          <select id="audit_outcome" value={outcomeFilter} onChange={(e) => setOutcomeFilter(e.target.value)}>
            <option value="">Todos</option>
            <option value="ok">Correcto</option>
            <option value="denied">Denegado</option>
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="audit_user">Usuario</label>
          <input id="audit_user" type="text" value={userFilter} onChange={(e) => setUserFilter(e.target.value)} placeholder="ej. admin" />
        </div>
        <div className={styles.field}>
          <label htmlFor="audit_from">Desde</label>
          <input id="audit_from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className={styles.field}>
          <label htmlFor="audit_to">Hasta</label>
          <input id="audit_to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
      </div>

      {data && (
        <p>
          Mostrando {data.total_matching} de {data.total_available} eventos.
        </p>
      )}

      {isLoading && !data ? (
        <p>Cargando…</p>
      ) : !error && data?.items.length === 0 ? (
        <p>Sin eventos registrados con los filtros actuales.</p>
      ) : (
        data && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Evento</th>
                  <th>Resultado</th>
                  <th>Usuario</th>
                  <th>Detalle</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((e, i) => (
                  <tr key={i}>
                    <td>{e.ts}</td>
                    <td>{EVENT_LABELS[e.event] ?? e.event}</td>
                    <td className={e.outcome === "denied" ? styles.deniedOutcome : undefined}>{e.outcome}</td>
                    <td>{e.user}</td>
                    <td>{e.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </section>
  );
}
