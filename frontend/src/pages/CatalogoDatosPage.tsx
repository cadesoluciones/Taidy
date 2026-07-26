import { useEffect, useState } from "react";

import { fetchBcTablesFull, fetchFactorialTablesFull, type BcTableConfig, type FactorialTableConfig } from "../api/meta";
import formStyles from "../components/Form.module.css";
import styles from "./CatalogoDatosPage.module.css";

export function CatalogoDatosPage() {
  const [bcTables, setBcTables] = useState<BcTableConfig[]>([]);
  const [factorialTables, setFactorialTables] = useState<FactorialTableConfig[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchBcTablesFull(), fetchFactorialTablesFull()])
      .then(([bc, factorial]) => {
        if (cancelled) return;
        setBcTables(bc.items);
        setFactorialTables(factorial.items);
      })
      .catch(() => {
        if (!cancelled) setError("No se pudo cargar el catálogo de datos.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section>
      <h1>Catálogo de datos</h1>
      <p>
        Qué tablas extrae Taidy de cada origen y con qué configuración, en modo solo lectura. Para añadir, editar o
        borrar tablas, ve a "Conexiones API" (Administración).
      </p>

      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {isLoading && !error && <p>Cargando…</p>}

      {!isLoading && !error && (
        <>
          <h2>Business Central</h2>
          {bcTables.length === 0 ? (
            <p>No hay tablas de Business Central configuradas todavía.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Nombre</th>
                    <th>Descripción</th>
                    <th>URL OData</th>
                    <th>Incremental</th>
                  </tr>
                </thead>
                <tbody>
                  {bcTables.map((t) => (
                    <tr key={t.name}>
                      <td>{t.name}</td>
                      <td>{t.description || "—"}</td>
                      <td className={styles.mono}>{t.url}</td>
                      <td>
                        <span className={t.incremental ? styles.badgeYes : styles.badgeNo}>
                          {t.incremental ? "Sí" : "No"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h2>Factorial HR</h2>
          {factorialTables.length === 0 ? (
            <p>No hay tablas de Factorial configuradas todavía.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Nombre</th>
                    <th>Descripción</th>
                    <th>Ruta de la API</th>
                    <th>Campos</th>
                    <th>Incremental</th>
                  </tr>
                </thead>
                <tbody>
                  {factorialTables.map((t) => (
                    <tr key={t.name}>
                      <td>{t.name}</td>
                      <td>{t.description || "—"}</td>
                      <td className={styles.mono}>{t.path}</td>
                      <td className={styles.mono}>{t.fields.join(", ")}</td>
                      <td>
                        <span className={t.incremental ? styles.badgeYes : styles.badgeNo}>
                          {t.incremental ? "Sí" : "No"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
