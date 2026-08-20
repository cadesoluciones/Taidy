import { useEffect, useMemo, useState } from "react";

import { ROLE_ADMIN, ROLE_OPERATOR } from "../api/auth";
import { ApiError } from "../api/client";
import {
  fetchFabricCatalog,
  updateFabricCatalogItem,
  type FabricCatalogItem,
  type FabricRelationship,
  type FabricRelationshipType,
} from "../api/fabricCatalog";
import { useAuth } from "../auth/AuthContext";
import styles from "./FabricCatalogManager.module.css";
import formStyles from "./Form.module.css";

const RELATIONSHIP_LABELS: Record<FabricRelationshipType, string> = {
  reads_from: "Lee de",
  writes_to: "Escribe en",
  triggered_by: "Se lanza tras",
};

function folderKey(path: string[]): string {
  return path.length > 0 ? path.join(" / ") : "(raíz del workspace)";
}

export function FabricCatalogManager() {
  const { user } = useAuth();
  const canEdit = user?.role === ROLE_ADMIN || user?.role === ROLE_OPERATOR;

  const [items, setItems] = useState<FabricCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [relationshipsDraft, setRelationshipsDraft] = useState<FabricRelationship[]>([]);
  const [newRelType, setNewRelType] = useState<FabricRelationshipType>("reads_from");
  const [targetPickerOpen, setTargetPickerOpen] = useState(false);
  const [targetSearch, setTargetSearch] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function reload() {
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
  }

  useEffect(() => {
    void reload();
  }, []);

  const selected = items.find((i) => i.item_id === selectedId) ?? null;

  useEffect(() => {
    setDescriptionDraft(selected?.description ?? "");
    setRelationshipsDraft(selected?.relationships ?? []);
    setSaveError(null);
    setSaveSuccess(null);
    setTargetPickerOpen(false);
    setTargetSearch("");
    // Only reset the draft when the SELECTED item changes, not on every
    // keystroke (selected is a fresh object each render via items.find()).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.item_id]);

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => i.name.toLowerCase().includes(q) || i.type.toLowerCase().includes(q));
  }, [items, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, FabricCatalogItem[]>();
    for (const item of filteredItems) {
      const key = folderKey(item.folder_path);
      const bucket = map.get(key);
      if (bucket) bucket.push(item);
      else map.set(key, [item]);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredItems]);

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

  const targetCandidates = useMemo(() => {
    if (!selected) return [];
    const q = targetSearch.trim().toLowerCase();
    return items.filter((i) => {
      if (i.item_id === selected.item_id) return false;
      if (!q) return true;
      return i.name.toLowerCase().includes(q) || i.type.toLowerCase().includes(q);
    });
  }, [items, selected, targetSearch]);

  function addRelationship(targetId: string) {
    setRelationshipsDraft((prev) => [...prev, { type: newRelType, target_item_id: targetId }]);
    setTargetPickerOpen(false);
    setTargetSearch("");
  }

  function removeRelationshipDraft(index: number) {
    setRelationshipsDraft((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSave() {
    if (!selected) return;
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      await updateFabricCatalogItem(selected.item_id, descriptionDraft, relationshipsDraft);
      setItems((prev) =>
        prev.map((i) =>
          i.item_id === selected.item_id
            ? { ...i, description: descriptionDraft, relationships: relationshipsDraft }
            : i,
        ),
      );
      setSaveSuccess("Guardado.");
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "No se pudo guardar.");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <p>Cargando catálogo de Fabric…</p>;
  if (loadError) return <div className={formStyles.errorBanner}>{loadError}</div>;

  return (
    <div className={styles.wrapper}>
      <input
        type="text"
        placeholder="Buscar por nombre o tipo…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className={styles.search}
      />

      <div className={styles.groups}>
        {grouped.map(([folder, folderItems]) => (
          <div key={folder} className={styles.folderGroup}>
            <div className={styles.folderLabel}>{folder}</div>
            <div className={styles.grid}>
              {folderItems.map((item) => {
                const relCount = relationshipCountByItem.get(item.item_id) ?? 0;
                return (
                  <button
                    key={item.item_id}
                    type="button"
                    className={item.item_id === selectedId ? styles.blockActive : styles.block}
                    onClick={() => setSelectedId(item.item_id)}
                  >
                    <strong className={styles.blockName}>{item.name}</strong>
                    <span className={styles.blockSubtitle}>
                      {item.type}
                      {relCount > 0 && ` · ${relCount} relación${relCount === 1 ? "" : "es"}`}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        {grouped.length === 0 && <p className={formStyles.hint}>Sin resultados.</p>}
      </div>

      {selected && (
        <div className={formStyles.card}>
          <div className={styles.detailHead}>
            <strong>{selected.name}</strong>
            <span className={styles.blockSubtitle}>{selected.type}</span>
          </div>
          {selected.folder_path.length > 0 && <p className={styles.breadcrumb}>{selected.folder_path.join(" / ")}</p>}

          <div className={formStyles.field}>
            <label htmlFor="fc_description">Descripción</label>
            <textarea
              id="fc_description"
              rows={4}
              value={descriptionDraft}
              onChange={(e) => setDescriptionDraft(e.target.value)}
              disabled={!canEdit}
            />
          </div>

          <div className={formStyles.field}>
            <label>Relaciones</label>
            <div className={styles.grid}>
              {relationshipsDraft.map((rel, i) => {
                const target = items.find((it) => it.item_id === rel.target_item_id);
                return (
                  <div key={`${rel.type}-${rel.target_item_id}-${i}`} className={styles.relBlock}>
                    {canEdit && (
                      <button
                        type="button"
                        className={styles.relRemove}
                        aria-label="Quitar relación"
                        onClick={() => removeRelationshipDraft(i)}
                      >
                        ×
                      </button>
                    )}
                    <strong className={styles.blockName}>{target?.name ?? rel.target_item_id}</strong>
                    <span className={styles.blockSubtitle}>{RELATIONSHIP_LABELS[rel.type]}</span>
                  </div>
                );
              })}
              {canEdit && (
                <button
                  type="button"
                  className={styles.addBlock}
                  onClick={() => setTargetPickerOpen((v) => !v)}
                >
                  + Añadir relación
                </button>
              )}
            </div>
            {relationshipsDraft.length === 0 && !targetPickerOpen && (
              <p className={formStyles.hint}>Sin relaciones declaradas.</p>
            )}

            {targetPickerOpen && (
              <div className={styles.targetPicker}>
                <div className={styles.relTypeToggle}>
                  {Object.entries(RELATIONSHIP_LABELS).map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      className={newRelType === key ? styles.relTypeActive : styles.relType}
                      onClick={() => setNewRelType(key as FabricRelationshipType)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <input
                  type="text"
                  placeholder="Buscar el elemento a relacionar…"
                  value={targetSearch}
                  onChange={(e) => setTargetSearch(e.target.value)}
                  className={styles.search}
                />
                <div className={styles.grid}>
                  {targetCandidates.slice(0, 30).map((candidate) => (
                    <button
                      key={candidate.item_id}
                      type="button"
                      className={styles.block}
                      onClick={() => addRelationship(candidate.item_id)}
                    >
                      <strong className={styles.blockName}>{candidate.name}</strong>
                      <span className={styles.blockSubtitle}>{candidate.type}</span>
                    </button>
                  ))}
                </div>
                {targetCandidates.length === 0 && <p className={formStyles.hint}>Sin resultados.</p>}
              </div>
            )}
          </div>

          {canEdit && (
            <>
              {saveSuccess && <div className={formStyles.successBanner}>{saveSuccess}</div>}
              {saveError && <div className={formStyles.errorBanner}>{saveError}</div>}
              <button type="button" className={formStyles.submit} onClick={() => void handleSave()} disabled={isSaving}>
                {isSaving ? "Guardando…" : "Guardar"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
