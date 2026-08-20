import { useEffect, useMemo, useRef, useState } from "react";

import { ChevronDown, Eye, EyeOff, Star } from "lucide-react";

import type { FabricCatalogItem } from "../api/fabricCatalog";
import { fabricIconFor } from "../utils/fabricIcons";
import formStyles from "./Form.module.css";
import styles from "./FabricCatalogManager.module.css";

const CRITICALITY_COLORS: Record<string, string> = {
  baja: "#8a9a5b",
  media: "#d9a441",
  alta: "#c0392b",
};

function folderKey(path: string[]): string {
  return path.length > 0 ? path.join(" / ") : "(raíz del workspace)";
}

interface FabricCatalogBrowserProps {
  items: FabricCatalogItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** Quick favorite/hide toggles on each block only render when these are
   * provided -- pages that only browse (e.g. Análisis de impacto) can skip
   * them instead of exposing an editing action they don't need. */
  onToggleFavorite?: (item: FabricCatalogItem) => void;
  onToggleHidden?: (item: FabricCatalogItem) => void;
  actionError?: string | null;
  /** Extra controls rendered between the search row and the folder groups
   * (e.g. Gobernanza's "+ Bloque personalizado" form). */
  headerExtra?: React.ReactNode;
}

/** The same compact, folder-grouped, collapsible block list Gobernanza de
 * datos uses -- shared so any page that lets someone pick a catalog item
 * looks and behaves the same way, instead of drifting into its own simpler
 * flat list. */
export function FabricCatalogBrowser({
  items,
  selectedId,
  onSelect,
  onToggleFavorite,
  onToggleHidden,
  actionError,
  headerExtra,
}: FabricCatalogBrowserProps) {
  const [search, setSearch] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());
  const hasAutoCollapsedRef = useRef(false);

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      if (item.is_hidden && !showHidden) return false;
      if (!q) return true;
      return item.name.toLowerCase().includes(q) || item.type.toLowerCase().includes(q);
    });
  }, [items, search, showHidden]);

  const grouped = useMemo(() => {
    const map = new Map<string, FabricCatalogItem[]>();
    for (const item of filteredItems) {
      const key = folderKey(item.folder_path);
      const bucket = map.get(key);
      if (bucket) bucket.push(item);
      else map.set(key, [item]);
    }
    const sorted = Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
    const favorites = filteredItems.filter((i) => i.is_favorite);
    return favorites.length > 0 ? ([["★ Favoritos", favorites], ...sorted] as [string, FabricCatalogItem[]][]) : sorted;
  }, [filteredItems]);

  useEffect(() => {
    if (hasAutoCollapsedRef.current || grouped.length === 0) return;
    hasAutoCollapsedRef.current = true;
    setCollapsedFolders(new Set(grouped.map(([key]) => key)));
  }, [grouped]);

  function toggleFolder(key: string) {
    setCollapsedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const relationshipCountByItem = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of items) {
      counts.set(item.item_id, (counts.get(item.item_id) ?? 0) + item.relationships.length);
      for (const rel of item.relationships) {
        counts.set(rel.target_item_id, (counts.get(rel.target_item_id) ?? 0) + 1);
      }
    }
    return counts;
  }, [items]);

  return (
    <div className={styles.listColumn}>
      <div className={styles.searchRow}>
        <input
          type="text"
          placeholder="Buscar por nombre o tipo…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className={styles.search}
        />
        <button
          type="button"
          className={showHidden ? styles.showHiddenToggleActive : styles.showHiddenToggle}
          onClick={() => setShowHidden((v) => !v)}
          title={showHidden ? "Ocultar los elementos marcados como ocultos" : "Mostrar los elementos ocultos"}
          aria-label="Mostrar/ocultar elementos ocultos"
        >
          {showHidden ? <Eye size={14} /> : <EyeOff size={14} />}
        </button>
      </div>

      {actionError && <div className={formStyles.errorBanner}>{actionError}</div>}

      {headerExtra}

      <div className={styles.groups}>
        {grouped.map(([folder, folderItems]) => {
          const collapsed = collapsedFolders.has(folder);
          return (
            <div key={folder} className={styles.folderGroup}>
              <button type="button" className={styles.folderHeader} onClick={() => toggleFolder(folder)}>
                <ChevronDown
                  size={12}
                  className={collapsed ? `${styles.folderChevron} ${styles.folderChevronCollapsed}` : styles.folderChevron}
                />
                <span className={styles.folderLabel}>
                  {folder} ({folderItems.length})
                </span>
              </button>
              {!collapsed && (
                <div className={styles.grid}>
                  {folderItems.map((item) => {
                    const relCount = relationshipCountByItem.get(item.item_id) ?? 0;
                    const ItemIcon = item.icon ? fabricIconFor(item.icon) : null;
                    return (
                      <div key={item.item_id} className={styles.blockWrapper}>
                        <button
                          type="button"
                          className={item.item_id === selectedId ? styles.blockActive : styles.block}
                          style={item.color ? { borderLeftColor: item.color } : undefined}
                          onClick={() => onSelect(item.item_id)}
                        >
                          <div className={styles.blockNameRow}>
                            {item.criticality && (
                              <span
                                className={styles.criticalityDot}
                                style={{ background: CRITICALITY_COLORS[item.criticality] }}
                              />
                            )}
                            {ItemIcon && <ItemIcon size={12} />}
                            <strong className={styles.blockName}>{item.name}</strong>
                          </div>
                          <span className={styles.blockSubtitle}>
                            {item.type}
                            {relCount > 0 && ` · ${relCount}`}
                          </span>
                        </button>
                        {(onToggleFavorite || onToggleHidden) && (
                          <div className={styles.blockQuickActions}>
                            {onToggleFavorite && (
                              <button
                                type="button"
                                className={item.is_favorite ? styles.blockQuickActionOn : styles.blockQuickAction}
                                onClick={() => onToggleFavorite(item)}
                                title="Marcar como favorito"
                                aria-label="Marcar como favorito"
                              >
                                <Star size={9} fill={item.is_favorite ? "currentColor" : "none"} />
                              </button>
                            )}
                            {onToggleHidden && (
                              <button
                                type="button"
                                className={item.is_hidden ? styles.blockQuickActionOn : styles.blockQuickAction}
                                onClick={() => onToggleHidden(item)}
                                title={item.is_hidden ? "Mostrar" : "Ocultar"}
                                aria-label="Ocultar o mostrar"
                              >
                                {item.is_hidden ? <EyeOff size={9} /> : <Eye size={9} />}
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
        {grouped.length === 0 && <p className={formStyles.hint}>Sin resultados.</p>}
      </div>
    </div>
  );
}
