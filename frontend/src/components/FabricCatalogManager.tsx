import { useEffect, useMemo, useState } from "react";

import { ChevronDown, Trash2 } from "lucide-react";

import { ROLE_ADMIN, ROLE_OPERATOR } from "../api/auth";
import { ApiError } from "../api/client";
import {
  createCustomFabricItem,
  deleteCustomFabricItem,
  fetchFabricCatalog,
  updateFabricCatalogItem,
  type FabricCatalogItem,
  type FabricCriticality,
  type FabricRelationship,
  type FabricRelationshipType,
  type FabricStatus,
} from "../api/fabricCatalog";
import { useAuth } from "../auth/AuthContext";
import { renderMarkdown } from "../utils/markdown";
import { ConfirmDialog } from "./ConfirmDialog";
import { type DiagramStep, WorkflowDiagram } from "./WorkflowDiagram";
import { FreeTagInput } from "./FreeTagInput";
import styles from "./FabricCatalogManager.module.css";
import formStyles from "./Form.module.css";

const RELATIONSHIP_LABELS: Record<FabricRelationshipType, string> = {
  reads_from: "Lee de",
  writes_to: "Escribe en",
  triggered_by: "Se lanza tras",
};

const CRITICALITY_LABELS: Record<Exclude<FabricCriticality, "">, string> = {
  baja: "Baja",
  media: "Media",
  alta: "Alta",
};

const CRITICALITY_COLORS: Record<Exclude<FabricCriticality, "">, string> = {
  baja: "#8a9a5b",
  media: "#d9a441",
  alta: "#c0392b",
};

const STATUS_LABELS: Record<Exclude<FabricStatus, "">, string> = {
  activo: "Activo",
  en_desuso: "En desuso",
  deprecado: "Deprecado",
};

// How many hops (in either direction) around the selected item the
// relationship canvas shows -- bounded so it stays a readable "local
// neighborhood" instead of the whole (106-item) catalog graph.
const NEIGHBORHOOD_HOPS = 2;

function folderKey(path: string[]): string {
  return path.length > 0 ? path.join(" / ") : "(raíz del workspace)";
}

/** Directed producer -> consumer adjacency over the WHOLE catalog (not
 * scoped to one item), used for the impact-analysis summary. A relationship
 * always points from whoever produces/triggers to whoever consumes/is
 * triggered, regardless of which of the two items declared it:
 * "writes_to" is declared forward (owner -> target); "reads_from" and
 * "triggered_by" are declared backward (target -> owner). */
function buildImpactGraph(items: FabricCatalogItem[]): {
  forward: Map<string, Set<string>>;
  backward: Map<string, Set<string>>;
} {
  const forward = new Map<string, Set<string>>();
  const backward = new Map<string, Set<string>>();
  function addEdge(from: string, to: string) {
    if (!forward.has(from)) forward.set(from, new Set());
    forward.get(from)!.add(to);
    if (!backward.has(to)) backward.set(to, new Set());
    backward.get(to)!.add(from);
  }
  for (const item of items) {
    for (const rel of item.relationships) {
      if (rel.type === "writes_to") addEdge(item.item_id, rel.target_item_id);
      else addEdge(rel.target_item_id, item.item_id);
    }
  }
  return { forward, backward };
}

function reachable(startId: string, adjacency: Map<string, Set<string>>): Set<string> {
  const seen = new Set<string>();
  const stack = [startId];
  while (stack.length > 0) {
    const current = stack.pop() as string;
    for (const next of adjacency.get(current) ?? []) {
      if (next !== startId && !seen.has(next)) {
        seen.add(next);
        stack.push(next);
      }
    }
  }
  return seen;
}

export function FabricCatalogManager() {
  const { user } = useAuth();
  const canEdit = user?.role === ROLE_ADMIN || user?.role === ROLE_OPERATOR;

  const [items, setItems] = useState<FabricCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());

  const [shortDescriptionDraft, setShortDescriptionDraft] = useState("");
  const [longDescriptionDraft, setLongDescriptionDraft] = useState("");
  const [longDescriptionView, setLongDescriptionView] = useState<"editar" | "vista previa">("editar");
  const [ownersDraft, setOwnersDraft] = useState<string[]>([]);
  const [criticalityDraft, setCriticalityDraft] = useState<FabricCriticality>("");
  const [statusDraft, setStatusDraft] = useState<FabricStatus>("");
  const [tagsDraft, setTagsDraft] = useState<string[]>([]);
  const [relationshipsDraft, setRelationshipsDraft] = useState<FabricRelationship[]>([]);
  const [newRelType, setNewRelType] = useState<FabricRelationshipType>("reads_from");
  const [targetPickerOpen, setTargetPickerOpen] = useState(false);
  const [targetSearch, setTargetSearch] = useState("");
  const [edgeHint, setEdgeHint] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const [customFormOpen, setCustomFormOpen] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customType, setCustomType] = useState("");
  const [customError, setCustomError] = useState<string | null>(null);
  const [isCreatingCustom, setIsCreatingCustom] = useState(false);
  const [confirmDeleteCustomOpen, setConfirmDeleteCustomOpen] = useState(false);
  const [isDeletingCustom, setIsDeletingCustom] = useState(false);

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
    setShortDescriptionDraft(selected?.short_description ?? "");
    setLongDescriptionDraft(selected?.long_description_markdown ?? "");
    setLongDescriptionView("editar");
    setOwnersDraft(selected?.owners ?? []);
    setCriticalityDraft(selected?.criticality ?? "");
    setStatusDraft(selected?.status ?? "");
    setTagsDraft(selected?.tags ?? []);
    setRelationshipsDraft(selected?.relationships ?? []);
    setSaveError(null);
    setSaveSuccess(null);
    setTargetPickerOpen(false);
    setTargetSearch("");
    setEdgeHint(null);
    setConfirmDeleteCustomOpen(false);
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

  const targetCandidates = useMemo(() => {
    if (!selected) return [];
    const q = targetSearch.trim().toLowerCase();
    return items.filter((i) => {
      if (i.item_id === selected.item_id) return false;
      if (!q) return true;
      return i.name.toLowerCase().includes(q) || i.type.toLowerCase().includes(q);
    });
  }, [items, selected, targetSearch]);

  // The relationship canvas shows the selected item's local neighborhood
  // (up to 2 hops in either direction), not a strict hub-and-spoke -- a
  // chain or merge between two OTHER items shows up as a direct edge
  // between them even when neither is the selected item, exactly like it
  // would look browsing the same items from either end. It reflects the
  // in-progress draft (relationshipsDraft), not just what's saved, so
  // adding/removing a relationship below updates the picture immediately.
  const neighborDiagram = useMemo(() => {
    if (!selected) return { steps: [] as DiagramStep[] };
    const itemsForGraph = items.map((i) =>
      i.item_id === selected.item_id ? { ...i, relationships: relationshipsDraft } : i,
    );
    const byId = new Map(itemsForGraph.map((i) => [i.item_id, i]));
    const { forward, backward } = buildImpactGraph(itemsForGraph);

    // Undirected BFS just to decide which nodes are "close enough" to show
    // -- direction is only meaningful once we draw the actual edges below.
    const distance = new Map<string, number>([[selected.item_id, 0]]);
    let frontier = [selected.item_id];
    for (let hop = 0; hop < NEIGHBORHOOD_HOPS && frontier.length > 0; hop++) {
      const next: string[] = [];
      for (const id of frontier) {
        const neighborIds = new Set([...(forward.get(id) ?? []), ...(backward.get(id) ?? [])]);
        for (const neighborId of neighborIds) {
          if (!distance.has(neighborId)) {
            distance.set(neighborId, hop + 1);
            next.push(neighborId);
          }
        }
      }
      frontier = next;
    }

    const nodes = new Map<string, DiagramStep>();
    for (const id of distance.keys()) {
      const found = byId.get(id);
      nodes.set(id, {
        id,
        label: found?.name ?? id,
        action: id === selected.item_id ? `${selected.type} · seleccionado` : found?.type ?? "?",
        depends_on: [],
        trigger_rule: "all_success",
      });
    }

    function addDependency(dependentId: string, dependsOnId: string) {
      const node = nodes.get(dependentId);
      if (!node) return;
      if (!node.depends_on.includes(dependsOnId)) node.depends_on = [...node.depends_on, dependsOnId];
    }

    // Only relationships directly touching the selected item get a
    // "Lee de / Escribe en / ..." label on the OTHER node -- that's the
    // actionable one; a 2nd-hop node just shows its Fabric type.
    const directTouchLabels = new Map<string, Set<string>>();
    function addDirectTouchLabel(itemId: string, label: string) {
      const set = directTouchLabels.get(itemId) ?? new Set<string>();
      set.add(label);
      directTouchLabels.set(itemId, set);
    }

    // Draw every relationship whose BOTH ends made it into the gathered
    // neighborhood -- including ones between two non-selected items.
    for (const item of itemsForGraph) {
      if (!nodes.has(item.item_id)) continue;
      for (const rel of item.relationships) {
        if (!nodes.has(rel.target_item_id)) continue;
        if (rel.type === "writes_to") addDependency(rel.target_item_id, item.item_id);
        else addDependency(item.item_id, rel.target_item_id);

        if (item.item_id === selected.item_id) addDirectTouchLabel(rel.target_item_id, RELATIONSHIP_LABELS[rel.type]);
        else if (rel.target_item_id === selected.item_id) addDirectTouchLabel(item.item_id, RELATIONSHIP_LABELS[rel.type]);
      }
    }

    for (const [id, labels] of directTouchLabels) {
      const node = nodes.get(id);
      if (!node) continue;
      node.action = `${[...labels].join(" / ")} · ${node.action}`;
    }

    return { steps: [...nodes.values()] };
  }, [selected, items, relationshipsDraft]);

  const impact = useMemo(() => {
    if (!selected) return { upstream: [] as FabricCatalogItem[], downstream: [] as FabricCatalogItem[] };
    const { forward, backward } = buildImpactGraph(items);
    const byId = new Map(items.map((i) => [i.item_id, i]));
    const upstreamIds = reachable(selected.item_id, backward);
    const downstreamIds = reachable(selected.item_id, forward);
    return {
      upstream: [...upstreamIds].map((id) => byId.get(id)).filter((i): i is FabricCatalogItem => !!i),
      downstream: [...downstreamIds].map((id) => byId.get(id)).filter((i): i is FabricCatalogItem => !!i),
    };
  }, [selected, items]);

  function addRelationship(targetId: string) {
    setRelationshipsDraft((prev) => [...prev, { type: newRelType, target_item_id: targetId }]);
    setTargetPickerOpen(false);
    setTargetSearch("");
  }

  function removeRelationshipDraft(index: number) {
    setRelationshipsDraft((prev) => prev.filter((_, i) => i !== index));
  }

  function handleRemoveEdge(sourceId: string, targetId: string) {
    if (!selected || !canEdit) return;
    setEdgeHint(null);
    const index = relationshipsDraft.findIndex((rel) => {
      if (rel.type === "writes_to") return sourceId === selected.item_id && targetId === rel.target_item_id;
      return sourceId === rel.target_item_id && targetId === selected.item_id;
    });
    if (index === -1) {
      setEdgeHint("Esta relación la declara el otro elemento -- edítala desde su propia ficha.");
      return;
    }
    removeRelationshipDraft(index);
  }

  async function handleSave() {
    if (!selected) return;
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      const updated = await updateFabricCatalogItem(selected.item_id, {
        short_description: shortDescriptionDraft,
        long_description_markdown: longDescriptionDraft,
        owners: ownersDraft,
        criticality: criticalityDraft,
        status: statusDraft,
        tags: tagsDraft,
        relationships: relationshipsDraft,
      });
      setItems((prev) => prev.map((i) => (i.item_id === selected.item_id ? { ...i, ...updated } : i)));
      setSaveSuccess("Guardado.");
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "No se pudo guardar.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleCreateCustom() {
    setIsCreatingCustom(true);
    setCustomError(null);
    try {
      const created = await createCustomFabricItem(customName, customType);
      setItems((prev) => [...prev, created]);
      setSelectedId(created.item_id);
      setCustomFormOpen(false);
      setCustomName("");
      setCustomType("");
    } catch (err) {
      setCustomError(err instanceof ApiError ? err.message : "No se pudo crear el bloque.");
    } finally {
      setIsCreatingCustom(false);
    }
  }

  async function handleDeleteCustom() {
    if (!selected) return;
    setIsDeletingCustom(true);
    try {
      await deleteCustomFabricItem(selected.item_id);
      setItems((prev) => prev.filter((i) => i.item_id !== selected.item_id));
      setSelectedId(null);
    } finally {
      setIsDeletingCustom(false);
      setConfirmDeleteCustomOpen(false);
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

          {canEdit && (
            <>
              <button type="button" className={styles.addCustomBlock} onClick={() => setCustomFormOpen((v) => !v)}>
                + Bloque personalizado
              </button>
              {customFormOpen && (
                <div className={styles.customForm}>
                  <input
                    type="text"
                    placeholder="Nombre"
                    value={customName}
                    onChange={(e) => setCustomName(e.target.value)}
                  />
                  <input
                    type="text"
                    placeholder="Tipo (p. ej. Fuente externa)"
                    value={customType}
                    onChange={(e) => setCustomType(e.target.value)}
                  />
                  {customError && <div className={formStyles.errorBanner}>{customError}</div>}
                  <div className={styles.customFormActions}>
                    <button
                      type="button"
                      className={formStyles.submit}
                      onClick={() => void handleCreateCustom()}
                      disabled={isCreatingCustom || !customName.trim()}
                    >
                      {isCreatingCustom ? "Creando…" : "Crear"}
                    </button>
                    <button type="button" onClick={() => setCustomFormOpen(false)}>
                      Cancelar
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

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
                        return (
                          <button
                            key={item.item_id}
                            type="button"
                            className={item.item_id === selectedId ? styles.blockActive : styles.block}
                            onClick={() => setSelectedId(item.item_id)}
                          >
                            <strong className={styles.blockName}>
                              {item.criticality && (
                                <span
                                  className={styles.criticalityDot}
                                  style={{ background: CRITICALITY_COLORS[item.criticality] }}
                                />
                              )}
                              {item.name}
                            </strong>
                            <span className={styles.blockSubtitle}>
                              {item.type}
                              {relCount > 0 && ` · ${relCount}`}
                            </span>
                          </button>
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

        <div className={styles.detailColumn}>
          {selected && (
            <div className={`${formStyles.card} ${styles.detailCard}`}>
              <div className={styles.detailHead}>
                <strong>{selected.name}</strong>
                <span className={styles.blockSubtitle}>{selected.type}</span>
                {selected.is_custom && canEdit && (
                  <button
                    type="button"
                    className={styles.deleteCustomButton}
                    onClick={() => setConfirmDeleteCustomOpen(true)}
                  >
                    <Trash2 size={13} /> Eliminar bloque
                  </button>
                )}
              </div>
              {selected.folder_path.length > 0 && (
                <p className={styles.breadcrumb}>{selected.folder_path.join(" / ")}</p>
              )}

              <div className={styles.fieldsGrid}>
                <div className={styles.generalColumn}>
                  <div className={formStyles.field}>
                    <label htmlFor="fc_short_description">Descripción breve</label>
                    <input
                      id="fc_short_description"
                      type="text"
                      value={shortDescriptionDraft}
                      onChange={(e) => setShortDescriptionDraft(e.target.value)}
                      disabled={!canEdit}
                    />
                  </div>

                  <div className={styles.fieldRow}>
                    <div className={formStyles.field}>
                      <label htmlFor="fc_owners">Responsables</label>
                      <FreeTagInput
                        id="fc_owners"
                        selected={ownersDraft}
                        onChange={setOwnersDraft}
                        placeholder="+ Añadir responsable…"
                        emptyHint="Sin responsables asignados"
                      />
                    </div>
                    <div className={formStyles.field}>
                      <label htmlFor="fc_tags">Etiquetas</label>
                      <FreeTagInput
                        id="fc_tags"
                        selected={tagsDraft}
                        onChange={setTagsDraft}
                        placeholder="+ Añadir etiqueta…"
                        emptyHint="Sin etiquetas"
                      />
                    </div>
                  </div>

                  <div className={styles.fieldRow}>
                    <div className={formStyles.field}>
                      <label htmlFor="fc_criticality">Criticidad</label>
                      <select
                        id="fc_criticality"
                        value={criticalityDraft}
                        onChange={(e) => setCriticalityDraft(e.target.value as FabricCriticality)}
                        disabled={!canEdit}
                      >
                        <option value="">(sin definir)</option>
                        {Object.entries(CRITICALITY_LABELS).map(([key, label]) => (
                          <option key={key} value={key}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className={formStyles.field}>
                      <label htmlFor="fc_status">Estado</label>
                      <select
                        id="fc_status"
                        value={statusDraft}
                        onChange={(e) => setStatusDraft(e.target.value as FabricStatus)}
                        disabled={!canEdit}
                      >
                        <option value="">(sin definir)</option>
                        {Object.entries(STATUS_LABELS).map(([key, label]) => (
                          <option key={key} value={key}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className={formStyles.field}>
                    <label>Relaciones</label>
                    <div className={styles.diagramWrap}>
                      <WorkflowDiagram
                        steps={neighborDiagram.steps}
                        actionLabels={{}}
                        selectedStepId={selected.item_id}
                        {...(canEdit ? { onRemoveDependency: handleRemoveEdge } : {})}
                        readOnly={!canEdit}
                        height={220}
                        testId="fabric-catalog-relationship-diagram"
                      />
                    </div>
                    {edgeHint && <p className={formStyles.hint}>{edgeHint}</p>}

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

                  <details className={styles.impactBox} open={impact.upstream.length + impact.downstream.length > 0}>
                    <summary>
                      Análisis de impacto ({impact.upstream.length} de las que depende, {impact.downstream.length} que
                      dependen de este)
                    </summary>
                    {impact.upstream.length > 0 && (
                      <>
                        <p>Este elemento depende de:</p>
                        <ul className={styles.impactList}>
                          {impact.upstream.map((i) => (
                            <li key={i.item_id}>{i.name}</li>
                          ))}
                        </ul>
                      </>
                    )}
                    {impact.downstream.length > 0 && (
                      <>
                        <p>Si se modifica, podría afectar a:</p>
                        <ul className={styles.impactList}>
                          {impact.downstream.map((i) => (
                            <li key={i.item_id}>{i.name}</li>
                          ))}
                        </ul>
                      </>
                    )}
                    {impact.upstream.length === 0 && impact.downstream.length === 0 && (
                      <p>Sin relaciones declaradas todavía en ningún sentido.</p>
                    )}
                  </details>
                </div>

                <div className={styles.longDescColumn}>
                  <div className={styles.detailHead}>
                    <label htmlFor="fc_long_description" style={{ marginBottom: 0 }}>
                      Descripción detallada
                    </label>
                    <button
                      type="button"
                      className={styles.relType}
                      onClick={() => setLongDescriptionView((v) => (v === "editar" ? "vista previa" : "editar"))}
                    >
                      {longDescriptionView === "editar" ? "Ver vista previa" : "Volver a editar"}
                    </button>
                  </div>
                  {longDescriptionView === "editar" ? (
                    <textarea
                      id="fc_long_description"
                      rows={14}
                      value={longDescriptionDraft}
                      onChange={(e) => setLongDescriptionDraft(e.target.value)}
                      disabled={!canEdit}
                      placeholder={"Admite Markdown: # títulos, **negrita**, *cursiva*, - listas, [texto](url)"}
                    />
                  ) : (
                    <div
                      className={styles.mdPreview}
                      dangerouslySetInnerHTML={{
                        __html: renderMarkdown(longDescriptionDraft) || "<p><em>Vacío.</em></p>",
                      }}
                    />
                  )}
                </div>
              </div>

              {selected.reviewed_at && (
                <p className={styles.reviewedHint}>
                  Última revisión: {selected.reviewed_by} · {new Date(selected.reviewed_at).toLocaleString("es-ES")}
                </p>
              )}

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

      <ConfirmDialog
        open={confirmDeleteCustomOpen}
        title="Eliminar bloque personalizado"
        description={`"${selected?.name ?? ""}" se eliminará del catálogo. Esta acción no se puede deshacer.`}
        confirmLabel="Eliminar"
        busy={isDeletingCustom}
        onConfirm={() => void handleDeleteCustom()}
        onCancel={() => setConfirmDeleteCustomOpen(false)}
      />
    </div>
  );
}
