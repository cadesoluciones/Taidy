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
import { type DiagramStep, WorkflowDiagram } from "./WorkflowDiagram";

const RELATIONSHIP_LABELS: Record<FabricRelationshipType, string> = {
  reads_from: "Lee de",
  writes_to: "Escribe en",
  triggered_by: "Se lanza tras",
};

function folderKey(path: string[]): string {
  return path.length > 0 ? path.join(" / ") : "(raíz del workspace)";
}

/** Turns typed relationships into a DAG for WorkflowDiagram (reused as-is --
 * same "block" visual already used for flows and pipeline activities).
 * reads_from/triggered_by point upstream->this item; writes_to points
 * this item->target. Only items that declare or receive at least one
 * relationship are included, so the ~100 undocumented items in a real
 * workspace don't turn this into unreadable noise. */
function buildDiagramSteps(items: FabricCatalogItem[]): DiagramStep[] {
  const byId = new Map(items.map((i) => [i.item_id, i]));
  const upstream = new Map<string, Set<string>>();

  function addEdge(fromId: string, toId: string) {
    if (!upstream.has(toId)) upstream.set(toId, new Set());
    upstream.get(toId)?.add(fromId);
  }

  const involvedIds = new Set<string>();
  for (const item of items) {
    for (const rel of item.relationships) {
      if (!byId.has(rel.target_item_id)) continue; // dangling reference (renamed/deleted in Fabric) -- skip
      involvedIds.add(item.item_id);
      involvedIds.add(rel.target_item_id);
      if (rel.type === "writes_to") {
        addEdge(item.item_id, rel.target_item_id);
      } else {
        addEdge(rel.target_item_id, item.item_id);
      }
    }
  }

  return items
    .filter((i) => involvedIds.has(i.item_id))
    .map((i) => ({
      id: i.item_id,
      label: i.name,
      action: i.type,
      depends_on: Array.from(upstream.get(i.item_id) ?? []),
      trigger_rule: "all_success",
    }));
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
  const [newRelTarget, setNewRelTarget] = useState("");
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

  const diagramSteps = useMemo(() => buildDiagramSteps(items), [items]);
  const actionLabels = useMemo(() => Object.fromEntries(items.map((i) => [i.type, i.type])), [items]);

  function addRelationshipDraft() {
    if (!newRelTarget) return;
    setRelationshipsDraft((prev) => [...prev, { type: newRelType, target_item_id: newRelTarget }]);
    setNewRelTarget("");
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
      <div className={styles.layout}>
        <div className={styles.listColumn}>
          <input
            type="text"
            placeholder="Buscar por nombre o tipo…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={styles.search}
          />
          <div className={styles.tree}>
            {grouped.map(([folder, folderItems]) => (
              <div key={folder} className={styles.folderGroup}>
                <div className={styles.folderLabel}>{folder}</div>
                {folderItems.map((item) => (
                  <button
                    key={item.item_id}
                    type="button"
                    className={item.item_id === selectedId ? styles.itemActive : styles.item}
                    onClick={() => setSelectedId(item.item_id)}
                  >
                    <span className={styles.itemName}>{item.name}</span>
                    <span className={styles.itemType}>{item.type}</span>
                  </button>
                ))}
              </div>
            ))}
            {grouped.length === 0 && <p className={formStyles.hint}>Sin resultados.</p>}
          </div>
        </div>

        <div className={styles.detailColumn}>
          {!selected ? (
            <p>Selecciona un elemento de la lista para ver o editar su ficha.</p>
          ) : (
            <div className={formStyles.card}>
              <div className={styles.detailHead}>
                <strong>{selected.name}</strong>
                <span className={styles.itemType}>{selected.type}</span>
              </div>
              {selected.folder_path.length > 0 && (
                <p className={styles.breadcrumb}>{selected.folder_path.join(" / ")}</p>
              )}

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
                {relationshipsDraft.length === 0 ? (
                  <p className={formStyles.hint}>Sin relaciones declaradas.</p>
                ) : (
                  <ul className={styles.relList}>
                    {relationshipsDraft.map((rel, i) => {
                      const target = items.find((it) => it.item_id === rel.target_item_id);
                      return (
                        <li key={`${rel.type}-${rel.target_item_id}-${i}`} className={styles.relItem}>
                          <span>{RELATIONSHIP_LABELS[rel.type]}</span>
                          <strong>{target?.name ?? rel.target_item_id}</strong>
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
                        </li>
                      );
                    })}
                  </ul>
                )}
                {canEdit && (
                  <div className={styles.relAdd}>
                    <select
                      value={newRelType}
                      onChange={(e) => setNewRelType(e.target.value as FabricRelationshipType)}
                    >
                      {Object.entries(RELATIONSHIP_LABELS).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                    <select value={newRelTarget} onChange={(e) => setNewRelTarget(e.target.value)}>
                      <option value="">Selecciona un elemento…</option>
                      {items
                        .filter((i) => i.item_id !== selected.item_id)
                        .map((i) => (
                          <option key={i.item_id} value={i.item_id}>
                            {i.name} ({i.type})
                          </option>
                        ))}
                    </select>
                    <button
                      type="button"
                      className={formStyles.submit}
                      onClick={addRelationshipDraft}
                      disabled={!newRelTarget}
                    >
                      Añadir
                    </button>
                  </div>
                )}
              </div>

              {canEdit && (
                <>
                  {saveSuccess && <div className={formStyles.successBanner}>{saveSuccess}</div>}
                  {saveError && <div className={formStyles.errorBanner}>{saveError}</div>}
                  <button
                    type="button"
                    className={formStyles.submit}
                    onClick={() => void handleSave()}
                    disabled={isSaving}
                  >
                    {isSaving ? "Guardando…" : "Guardar"}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {diagramSteps.length > 0 && (
        <div className={styles.diagramSection}>
          <h3>Relaciones entre objetos</h3>
          <p className={formStyles.hint}>Solo se muestran los elementos con al menos una relación declarada.</p>
          <WorkflowDiagram
            steps={diagramSteps}
            actionLabels={actionLabels}
            readOnly
            height={420}
            selectedStepId={selectedId}
            onSelectStep={setSelectedId}
          />
        </div>
      )}
    </div>
  );
}
