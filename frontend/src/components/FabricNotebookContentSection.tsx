import { useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { fetchNotebookContent } from "../api/fabricCatalog";
import styles from "./FabricNotebookContentSection.module.css";
import formStyles from "./Form.module.css";

interface FabricNotebookContentSectionProps {
  itemId: string;
  /** True when the catalog item itself is "sin conexión" -- reading a
   * notebook's code is always a live get_definition() call, so there's
   * nothing useful this can do while that's the case. */
  offline?: boolean;
}

/** Read-only view of a single Notebook's own Python source. Prefers the
 * notebook-scan cache's own copy (the same get_definition() call
 * detect_relationships() already pays for when scanning every notebook at
 * once for "Detectar relaciones") -- usually instant; a cache miss falls
 * back to one live fetch that also fills the cache for next time. There's
 * no editing path here, and no corresponding block for anything that
 * isn't a Notebook -- the "Modelo semántico" tab hides itself outside
 * Lakehouse tables the same way, since it has nothing meaningful to show
 * there either. */
export function FabricNotebookContentSection({ itemId, offline = false }: FabricNotebookContentSectionProps) {
  const [content, setContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Same "ignore a slow response for an item that's no longer selected"
  // guard as FabricSemanticModelSection/FabricCatalogManifestSection.
  const currentItemIdRef = useRef(itemId);
  currentItemIdRef.current = itemId;

  async function load(refresh = false) {
    const requestedItemId = itemId;
    setIsLoading(true);
    setError(null);
    try {
      const result = await fetchNotebookContent(requestedItemId, refresh);
      if (currentItemIdRef.current !== requestedItemId) return;
      setContent(result.content);
    } catch (err) {
      if (currentItemIdRef.current !== requestedItemId) return;
      setError(err instanceof ApiError ? err.message : "No se pudo leer el contenido del notebook.");
    } finally {
      if (currentItemIdRef.current === requestedItemId) setIsLoading(false);
    }
  }

  useEffect(() => {
    setContent(null);
    if (offline) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemId, offline]);

  if (offline) {
    return (
      <p className={formStyles.hint}>
        Contenido no disponible: este notebook está sin conexión. Vuelve a intentarlo cuando Fabric lo liste de nuevo.
      </p>
    );
  }

  if (isLoading) return <p className={formStyles.hint}>Cargando contenido del notebook… puede tardar unos segundos si no está en caché.</p>;

  return (
    <div className={styles.wrap}>
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      {content !== null && (
        <div className={styles.toolbar}>
          <button
            type="button"
            className={styles.reloadButton}
            onClick={() => void load(true)}
            title="Vuelve a leer este notebook en directo desde Fabric y actualiza la caché"
          >
            Recargar
          </button>
        </div>
      )}
      {content !== null && <pre className={styles.code}>{content}</pre>}
    </div>
  );
}
