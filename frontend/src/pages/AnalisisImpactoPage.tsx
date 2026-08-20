import { useEffect, useMemo, useState } from "react";

import { fetchFabricCatalog, type FabricCatalogItem } from "../api/fabricCatalog";
import { ApiError } from "../api/client";
import { computeImpact } from "../utils/fabricImpact";
import formStyles from "../components/Form.module.css";
import styles from "./AnalisisImpactoPage.module.css";

export function AnalisisImpactoPage() {
  const [items, setItems] = useState<FabricCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setIsLoading(true);
      setLoadError(null);
      try {
        const res = await fetchFabricCatalog();
        setItems(res.items);
      } catch (err) {
        setLoadError(err instanceof ApiError ? err.message : "No se pudo cargar el catálogo de Fabric.");
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => i.name.toLowerCase().includes(q) || i.type.toLowerCase().includes(q));
  }, [items, search]);

  const selected = items.find((i) => i.item_id === selectedId) ?? null;
  const impact = useMemo(() => (selected ? computeImpact(items, selected.item_id) : null), [items, selected]);

  return (
    <section>
      <h1>Análisis de impacto</h1>
      <p>
        Elige un elemento del catálogo de Fabric para ver de qué depende y a qué otros elementos podría afectar si
        se modifica, a partir de las relaciones declaradas en "Gobernanza de datos".
      </p>

      {isLoading && <p>Cargando catálogo de Fabric…</p>}
      {loadError && <div className={formStyles.errorBanner}>{loadError}</div>}

      {!isLoading && !loadError && (
        <div className={styles.layout}>
          <div>
            <input
              type="text"
              placeholder="Buscar por nombre o tipo…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className={styles.search}
            />
            <div className={styles.list}>
              {filtered.map((item) => (
                <button
                  key={item.item_id}
                  type="button"
                  className={item.item_id === selectedId ? styles.itemActive : styles.item}
                  onClick={() => setSelectedId(item.item_id)}
                >
                  <strong>{item.name}</strong>
                  <span className={styles.itemSubtitle}>{item.type}</span>
                </button>
              ))}
              {filtered.length === 0 && <p className={styles.empty}>Sin resultados.</p>}
            </div>
          </div>

          {selected && impact && (
            <div className={styles.resultCard}>
              <h2>{selected.name}</h2>
              <p className={styles.itemSubtitle}>{selected.type}</p>
              <div className={styles.columns}>
                <div className={styles.column}>
                  <h3>Depende de ({impact.upstream.length})</h3>
                  {impact.upstream.length > 0 ? (
                    <ul className={styles.itemList}>
                      {impact.upstream.map((i) => (
                        <li key={i.item_id}>{i.name}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className={styles.empty}>No depende de ningún otro elemento declarado.</p>
                  )}
                </div>
                <div className={styles.column}>
                  <h3>Podría afectar a ({impact.downstream.length})</h3>
                  {impact.downstream.length > 0 ? (
                    <ul className={styles.itemList}>
                      {impact.downstream.map((i) => (
                        <li key={i.item_id}>{i.name}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className={styles.empty}>Ningún otro elemento declara depender de este.</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
