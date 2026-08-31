import { useEffect, useMemo, useRef, useState } from "react";

import { Boxes, ChevronDown, Eye, EyeOff, Star } from "lucide-react";

import type { FabricCatalogItem } from "../api/fabricCatalog";
import { fabricIconFor } from "../utils/fabricIcons";
import formStyles from "./Form.module.css";
import styles from "./FabricCatalogManager.module.css";

// Shown for a type with no configured default icon (a brand new Fabric item
// type this tenant just started using, before Configuración has a mapping
// for it) -- never persisted, just a rendering fallback.
const FALLBACK_TYPE_ICON = Boxes;

const CRITICALITY_COLORS: Record<string, string> = {
  baja: "#8a9a5b",
  media: "#d9a441",
  alta: "#c0392b",
};

const FAVORITES_KEY = "★ Favoritos";
// Sentinel for "no sub-path" -- an item that sits directly under its
// system (e.g. a plain Fabric item with no subfolder) renders right under
// the top-level group instead of behind a pointless one-item sub-header.
const ROOT_SUBKEY = "";

interface TopGroup {
  key: string;
  subGroups: [string, FabricCatalogItem[]][];
}

/** Two levels, not one flat key per distinct folder_path -- everything
 * from the same system (Fabric/Business Central/HubSpot/Factorial/
 * Personalizados) collapses under ONE top-level row, with its own
 * subfolders nested inside instead of each combination getting its own
 * top-level row (which is how "Fabric", "Fabric / EDA" and
 * "Fabric / ETLs Medallion / Bronze" ended up as three unrelated-looking
 * rows before this). The remaining path (however many levels deep) is
 * still shown verbatim as the sub-group's label, so where something comes
 * from stays legible. */
function groupByTopAndRest(items: FabricCatalogItem[]): TopGroup[] {
  const topMap = new Map<string, Map<string, FabricCatalogItem[]>>();
  for (const item of items) {
    const path = item.folder_path.length > 0 ? item.folder_path : ["(raíz del workspace)"];
    const top = path[0]!; // path is never empty -- the ternary above guarantees at least one entry
    const subKey = path.slice(1).join(" / ");
    if (!topMap.has(top)) topMap.set(top, new Map());
    const subMap = topMap.get(top)!;
    const bucket = subMap.get(subKey);
    if (bucket) bucket.push(item);
    else subMap.set(subKey, [item]);
  }
  return Array.from(topMap.entries())
    .map(([top, subMap]) => ({
      key: top,
      subGroups: Array.from(subMap.entries()).sort(([a], [b]) => a.localeCompare(b)),
    }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

function subGroupKey(topKey: string, subKey: string): string {
  return `${topKey} :: ${subKey}`;
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
  /** Default icon key per item type (Notebook, Lakehouse, Tabla, ...) --
   * feeds both the quick-filter row's buttons and the fallback icon shown
   * on a block that has no icon of its own. Configured in Configuración,
   * see fetchTypeIcons(). A type with no entry here still gets a filter
   * button, just with a generic placeholder icon. */
  typeIcons?: Record<string, string>;
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
  typeIcons = {},
}: FabricCatalogBrowserProps) {
  const [search, setSearch] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());
  const hasAutoCollapsedRef = useRef(false);

  // Counted off `items` filtered only by "mostrar ocultos" (not by search
  // text or the type filter itself) -- these buttons are the available
  // facets, so their counts stay stable reference numbers ("hay 5 tablas")
  // rather than shrinking as soon as one is clicked.
  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of items) {
      if (item.is_hidden && !showHidden) continue;
      counts.set(item.type, (counts.get(item.type) ?? 0) + 1);
    }
    return Array.from(counts.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [items, showHidden]);

  function toggleType(type: string) {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      if (item.is_hidden && !showHidden) return false;
      if (activeTypes.size > 0 && !activeTypes.has(item.type)) return false;
      if (!q) return true;
      return item.name.toLowerCase().includes(q) || item.type.toLowerCase().includes(q);
    });
  }, [items, search, showHidden, activeTypes]);

  const grouped = useMemo(() => {
    const favorites = filteredItems.filter((i) => i.is_favorite);
    const rest = groupByTopAndRest(filteredItems);
    if (favorites.length === 0) return rest;
    const favoriteGroup: TopGroup = { key: FAVORITES_KEY, subGroups: [[ROOT_SUBKEY, favorites]] };
    return [favoriteGroup, ...rest];
  }, [filteredItems]);

  // First load only: start every group (top-level AND nested sub-groups)
  // collapsed so the sidebar opens short instead of dumping every item at
  // once -- later toggles (by the user, or a group appearing/disappearing
  // as favorites change) are left alone.
  useEffect(() => {
    if (hasAutoCollapsedRef.current || grouped.length === 0) return;
    hasAutoCollapsedRef.current = true;
    const keys = new Set<string>();
    for (const top of grouped) {
      keys.add(top.key);
      for (const [subKey] of top.subGroups) {
        if (subKey !== ROOT_SUBKEY) keys.add(subGroupKey(top.key, subKey));
      }
    }
    setCollapsedFolders(keys);
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

  function renderBlock(item: FabricCatalogItem) {
    const relCount = relationshipCountByItem.get(item.item_id) ?? 0;
    const iconKey = item.icon || typeIcons[item.type];
    const ItemIcon = iconKey ? fabricIconFor(iconKey) : null;
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
              <span className={styles.criticalityDot} style={{ background: CRITICALITY_COLORS[item.criticality] }} />
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
  }

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

      {typeCounts.length > 0 && (
        <div className={styles.typeFilterRow}>
          {typeCounts.map(([type, count]) => {
            const iconKey = typeIcons[type];
            const TypeIcon = iconKey ? (fabricIconFor(iconKey) ?? FALLBACK_TYPE_ICON) : FALLBACK_TYPE_ICON;
            const active = activeTypes.has(type);
            return (
              <button
                key={type}
                type="button"
                className={active ? styles.typeFilterActive : styles.typeFilter}
                onClick={() => toggleType(type)}
                title={`${type} (${count})`}
                aria-label={`Filtrar por ${type}`}
                aria-pressed={active}
              >
                <TypeIcon size={13} />
                <span className={styles.typeFilterCount}>{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {actionError && <div className={formStyles.errorBanner}>{actionError}</div>}

      {headerExtra}

      <div className={styles.groups}>
        {grouped.map((top) => {
          const topCollapsed = collapsedFolders.has(top.key);
          const totalCount = top.subGroups.reduce((sum, [, subItems]) => sum + subItems.length, 0);
          return (
            <div key={top.key} className={styles.folderGroup}>
              <button type="button" className={styles.folderHeader} onClick={() => toggleFolder(top.key)}>
                <ChevronDown
                  size={12}
                  className={
                    topCollapsed ? `${styles.folderChevron} ${styles.folderChevronCollapsed}` : styles.folderChevron
                  }
                />
                <span className={styles.folderLabel}>
                  {top.key} ({totalCount})
                </span>
              </button>
              {!topCollapsed && (
                <div className={styles.subGroups}>
                  {top.subGroups.map(([subKey, subItems]) => {
                    if (subKey === ROOT_SUBKEY) {
                      return (
                        <div key={ROOT_SUBKEY} className={styles.grid}>
                          {subItems.map(renderBlock)}
                        </div>
                      );
                    }
                    const composite = subGroupKey(top.key, subKey);
                    const subCollapsed = collapsedFolders.has(composite);
                    return (
                      <div key={subKey} className={styles.folderGroup}>
                        <button type="button" className={styles.folderHeader} onClick={() => toggleFolder(composite)}>
                          <ChevronDown
                            size={11}
                            className={
                              subCollapsed
                                ? `${styles.folderChevron} ${styles.folderChevronCollapsed}`
                                : styles.folderChevron
                            }
                          />
                          <span className={styles.folderLabel}>
                            {subKey} ({subItems.length})
                          </span>
                        </button>
                        {!subCollapsed && <div className={styles.grid}>{subItems.map(renderBlock)}</div>}
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
