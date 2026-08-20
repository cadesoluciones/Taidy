import { useEffect, useMemo, useState } from "react";

import { ROLE_ADMIN, ROLE_OPERATOR } from "../api/auth";
import { ApiError } from "../api/client";
import {
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

  // The relationship canvas is scoped to direct neighbors of the selected
  // item only (matches the requested mockup) -- it reflects the in-progress
  // draft, not just what's saved, so adding/removing a relationship below
  // updates the picture immediately.
  const neighborDiagram = useMemo(() => {
    if (!selected) return { steps: [] as DiagramStep[] };
    const nodes = new Map<string, DiagramStep>();
    const labelsByNeighbor = new Map<string, Set<string>>();
    nodes.set(selected.item_id, {
      id: selected.item_id,
      label: selected.name,
      action: `${selected.type} · seleccionado`,
      depends_on: [],
      trigger_rule: "all_success",
    });

    function ensureNode(itemId: string) {
      if (nodes.has(itemId)) return;
      const found = items.find((i) => i.item_id === itemId);
      nodes.set(itemId, {
        id: itemId,
        label: found?.name ?? itemId,
        action: found?.type ?? "?",
        depends_on: [],
        trigger_rule: "all_success",
      });
    }

    function addLabel(itemId: string, label: string) {
      const set = labelsByNeighbor.get(itemId) ?? new Set<string>();
      set.add(label);
      labelsByNeighbor.set(itemId, set);
    }

    function addDependency(dependentId: string, dependsOnId: string) {
      const node = nodes.get(dependentId);
      if (!node) return;
      if (!node.depends_on.includes(dependsOnId)) node.depends_on = [...node.depends_on, dependsOnId];
    }

    for (const rel of relationshipsDraft) {
      ensureNode(rel.target_item_id);
      addLabel(rel.target_item_id, RELATIONSHIP_LABELS[rel.type]);
      if (rel.type === "writes_to") addDependency(rel.target_item_id, selected.item_id);
      else addDependency(selected.item_id, rel.target_item_id);
    }

    for (const other of items) {
      if (other.item_id === selected.item_id) continue;
      for (const rel of other.relationships) {
        if (rel.target_item_id !== selected.item_id) continue;
        ensureNode(other.item_id);
        addLabel(other.item_id, RELATIONSHIP_LABELS[rel.type]);
        if (rel.type === "writes_to") addDependency(selected.item_id, other.item_id);
        else addDependency(other.item_id, selected.item_id);
      }
    }

    for (const [id, node] of nodes) {
      if (id === selected.item_id) continue;
      const labels = [...(labelsByNeighbor.get(id) ?? [])].join(" / ");
      node.action = labels ? `${labels} · ${node.action}` : node.action;
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
                      {item.status && ` · ${STATUS_LABELS[item.status]}`}
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

          <div className={formStyles.field}>
            <div className={styles.detailHead}>
              <label htmlFor="fc_long_description" style={{ marginBottom: 0 }}>
                Descripción detallada
              </label>
              <div className={styles.relTypeToggle}>
                {(["editar", "vista previa"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className={longDescriptionView === mode ? styles.relTypeActive : styles.relType}
                    onClick={() => setLongDescriptionView(mode)}
                  >
                    {mode === "editar" ? "Editar" : "Vista previa"}
                  </button>
                ))}
              </div>
            </div>
            {longDescriptionView === "editar" ? (
              <textarea
                id="fc_long_description"
                rows={8}
                value={longDescriptionDraft}
                onChange={(e) => setLongDescriptionDraft(e.target.value)}
                disabled={!canEdit}
                placeholder={"Admite Markdown: # títulos, **negrita**, *cursiva*, - listas, [texto](url)"}
              />
            ) : (
              <div
                className={styles.mdPreview}
                dangerouslySetInnerHTML={{ __html: renderMarkdown(longDescriptionDraft) || "<p><em>Vacío.</em></p>" }}
              />
            )}
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
