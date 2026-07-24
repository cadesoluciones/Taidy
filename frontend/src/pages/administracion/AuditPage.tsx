import { useEffect, useState } from "react";

import { fetchAudit, type AuditPage as AuditPageData } from "../../api/audit";

export function AuditPage() {
  const [data, setData] = useState<AuditPageData | null>(null);

  useEffect(() => {
    fetchAudit().then(setData);
  }, []);

  return (
    <section>
      <h1>Auditoría de seguridad</h1>
      <p>Eventos de login, cierre de sesión y accesos denegados. Nunca contiene tokens ni secretos.</p>
      {!data ? (
        <p>Cargando…</p>
      ) : data.items.length === 0 ? (
        <p>Sin eventos registrados todavía.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                {["Fecha", "Evento", "Resultado", "Usuario", "Detalle"].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "6px 10px", borderBottom: "1px solid var(--color-border)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.map((e, i) => (
                <tr key={i}>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--color-border)" }}>{e.ts}</td>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--color-border)" }}>{e.event}</td>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--color-border)" }}>{e.outcome}</td>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--color-border)" }}>{e.user}</td>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--color-border)" }}>{e.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
