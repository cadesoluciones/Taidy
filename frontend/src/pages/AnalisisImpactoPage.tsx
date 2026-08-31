import { useEffect, useMemo, useState } from "react";

import { fetchFabricCatalog, type FabricCatalogItem } from "../api/fabricCatalog";
import { ApiError } from "../api/client";
import { FabricCatalogBrowser } from "../components/FabricCatalogBrowser";
import { FabricRelationshipCanvas } from "../components/FabricRelationshipCanvas";
import { computeImpact } from "../utils/fabricImpact";
import formStyles from "../components/Form.module.css";
import managerStyles from "../components/FabricCatalogManager.module.css";
import { PageHeader } from "../components/PageHeader";
import styles from "./AnalisisImpactoPage.module.css";

const MIN_DEPTH = 1;
const MAX_DEPTH = 10;
const DEFAULT_DEPTH = 3;

export function AnalisisImpactoPage() {
  const [items, setItems] = useState<FabricCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [depth, setDepth] = useState(DEFAULT_DEPTH);

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

  const selected = items.find((i) => i.item_id === selectedId) ?? null;
  const impact = useMemo(() => (selected ? computeImpact(items, selected.item_id) : null), [items, selected]);

  return (
    <section>
      <PageHeader
        title="Análisis de impacto"
        description={
          <>
            Elige un elemento del catálogo de Fabric para ver de qué depende y a qué otros elementos podría afectar
            si se modifica, a partir de las relaciones declaradas en "Gobernanza de datos".
          </>
        }
      />

      {isLoading && <p>Cargando catálogo de Fabric…</p>}
      {loadError && <div className={formStyles.errorBanner}>{loadError}</div>}

      {!isLoading && !loadError && (
        <div className={managerStyles.layout}>
          <FabricCatalogBrowser items={items} selectedId={selectedId} onSelect={setSelectedId} />

          <div className={managerStyles.detailColumn}>
            {selected && impact && (
              <div className={styles.resultCard}>
                <h2>{selected.name}</h2>
                <p className={styles.itemSubtitle}>{selected.type}</p>

                <div className={styles.graphHead}>
                  <h3>Mapa de dependencias</h3>
                  <div className={styles.depthControl}>
                    <span>Niveles</span>
                    <button
                      type="button"
                      onClick={() => setDepth((d) => Math.max(MIN_DEPTH, d - 1))}
                      disabled={depth <= MIN_DEPTH}
                      aria-label="Menos niveles"
                    >
                      −
                    </button>
                    <strong>{depth}</strong>
                    <button
                      type="button"
                      onClick={() => setDepth((d) => Math.min(MAX_DEPTH, d + 1))}
                      disabled={depth >= MAX_DEPTH}
                      aria-label="Más niveles"
                    >
                      +
                    </button>
                  </div>
                </div>
                <p className={styles.empty}>
                  Arrastra para mover el lienzo y usa la rueda del ratón para acercar. A mayor número de niveles,
                  aparecen más elementos relacionados entre sí (hasta {MAX_DEPTH}), pero el diagrama puede volverse
                  más denso.
                </p>
                <div className={managerStyles.diagramWrap}>
                  <FabricRelationshipCanvas
                    items={items}
                    centerId={selected.item_id}
                    canvasPositions={selected.canvas_positions}
                    interactive={false}
                    showControls
                    height="55vh"
                    hops={depth}
                    testId="impact-relationship-graph"
                  />
                </div>

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
        </div>
      )}
    </section>
  );
}
