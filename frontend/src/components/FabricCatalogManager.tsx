import { useEffect, useMemo, useRef, useState } from "react";

import { Eye, EyeOff, Palette, Printer, Star, Table2, Trash2, X } from "lucide-react";

import { ROLE_ADMIN, ROLE_OPERATOR } from "../api/auth";
import { ApiError } from "../api/client";
import {
  DATA_ROLE_FIELDS,
  LAKEHOUSE_TABLE_ID_PREFIX,
  addFabricRelationship,
  createCustomFabricItem,
  deleteCustomFabricItem,
  fetchFabricCatalog,
  fetchFabricTablePreview,
  fetchTypeIcons,
  removeFabricRelationship,
  setFabricCanvasPositions,
  setFabricFavorite,
  setFabricHidden,
  updateFabricCatalogItem,
  type DataRoleField,
  type FabricCanvasPosition,
  type FabricCatalogItem,
  type FabricCriticality,
  type FabricRelationshipType,
  type FabricStatus,
  type FabricTablePreview,
} from "../api/fabricCatalog";
import { useAuth } from "../auth/AuthContext";
import { renderMarkdown } from "../utils/markdown";
import { FABRIC_ICON_OPTIONS, fabricIconFor } from "../utils/fabricIcons";
import { DATA_ROLE_INFO } from "../utils/dataRoles";
import { ConfirmDialog } from "./ConfirmDialog";
import { FabricCatalogBrowser } from "./FabricCatalogBrowser";
import { FabricRelationshipCanvas } from "./FabricRelationshipCanvas";
import { FabricSemanticModelSection } from "./FabricSemanticModelSection";
import { FreeTagInput } from "./FreeTagInput";
import { Modal } from "./Modal";
import styles from "./FabricCatalogManager.module.css";
import formStyles from "./Form.module.css";

const CRITICALITY_LABELS: Record<Exclude<FabricCriticality, "">, string> = {
  baja: "Baja",
  media: "Media",
  alta: "Alta",
};

const STATUS_LABELS: Record<Exclude<FabricStatus, "">, string> = {
  activo: "Activo",
  en_desuso: "En desuso",
  deprecado: "Deprecado",
};

const EMPTY_ROLE_DRAFTS: Record<DataRoleField, string[]> = {
  data_owner: [],
  data_steward: [],
  data_custodian: [],
  data_consumer: [],
};

function arraysEqual(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

export function FabricCatalogManager() {
  const { user } = useAuth();
  const canEdit = user?.role === ROLE_ADMIN || user?.role === ROLE_OPERATOR;

  const [items, setItems] = useState<FabricCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [typeIcons, setTypeIcons] = useState<Record<string, string>>({});

  const [shortDescriptionDraft, setShortDescriptionDraft] = useState("");
  const [longDescriptionDraft, setLongDescriptionDraft] = useState("");
  const [longDescriptionView, setLongDescriptionView] = useState<"editar" | "vista previa">("editar");
  const [detailTab, setDetailTab] = useState<"descripcion" | "modelo">("descripcion");
  // Tracks whether the semantic-model tab has been opened at least once for
  // the CURRENTLY selected item -- once true, FabricSemanticModelSection
  // stays mounted (just CSS-hidden) across further tab switches instead of
  // unmounting, so its already-fetched state survives instead of refetching
  // from Fabric (confirmed live: getDefinition alone can take ~20s) every
  // single time the user tabs back to it. Reset to false whenever the
  // selected item changes, so a genuinely different table still fetches
  // fresh the first time, not stale data left over from mounting once.
  const [hasOpenedModeloTab, setHasOpenedModeloTab] = useState(false);
  const [roleDrafts, setRoleDrafts] = useState<Record<DataRoleField, string[]>>(EMPTY_ROLE_DRAFTS);
  const [criticalityDraft, setCriticalityDraft] = useState<FabricCriticality>("");
  const [statusDraft, setStatusDraft] = useState<FabricStatus>("");
  const [tagsDraft, setTagsDraft] = useState<string[]>([]);
  const [colorDraft, setColorDraft] = useState("");
  const [iconDraft, setIconDraft] = useState("");
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const appearanceRef = useRef<HTMLDivElement>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const [relationshipModalOpen, setRelationshipModalOpen] = useState(false);
  const [canvasError, setCanvasError] = useState<string | null>(null);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewItemId, setPreviewItemId] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<FabricTablePreview | null>(null);

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
    fetchTypeIcons()
      .then((res) => setTypeIcons(res.icons))
      .catch(() => setTypeIcons({}));
  }, []);

  // Close the appearance popover when clicking anywhere outside it.
  useEffect(() => {
    if (!appearanceOpen) return;
    function handleClick(e: MouseEvent) {
      if (appearanceRef.current && !appearanceRef.current.contains(e.target as Node)) setAppearanceOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [appearanceOpen]);

  const selected = items.find((i) => i.item_id === selectedId) ?? null;

  useEffect(() => {
    setShortDescriptionDraft(selected?.short_description ?? "");
    setLongDescriptionDraft(selected?.long_description_markdown ?? "");
    setLongDescriptionView("editar");
    setDetailTab("descripcion");
    setHasOpenedModeloTab(false);
    setRoleDrafts({
      data_owner: selected?.data_owner ?? [],
      data_steward: selected?.data_steward ?? [],
      data_custodian: selected?.data_custodian ?? [],
      data_consumer: selected?.data_consumer ?? [],
    });
    setCriticalityDraft(selected?.criticality ?? "");
    setStatusDraft(selected?.status ?? "");
    setTagsDraft(selected?.tags ?? []);
    setColorDraft(selected?.color ?? "");
    setIconDraft(selected?.icon ?? "");
    setAppearanceOpen(false);
    setSaveError(null);
    setSaveSuccess(null);
    setCanvasError(null);
    setRelationshipModalOpen(false);
    setConfirmDeleteCustomOpen(false);
    setPreviewOpen(false);
    setPreviewError(null);
    setPreviewData(null);
    // Only reset the draft when the SELECTED item changes, not on every
    // keystroke (selected is a fresh object each render via items.find()).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.item_id]);

  const isDirty = useMemo(() => {
    if (!selected) return false;
    return (
      shortDescriptionDraft !== selected.short_description ||
      longDescriptionDraft !== selected.long_description_markdown ||
      criticalityDraft !== selected.criticality ||
      statusDraft !== selected.status ||
      colorDraft !== selected.color ||
      iconDraft !== selected.icon ||
      !arraysEqual(tagsDraft, selected.tags) ||
      DATA_ROLE_FIELDS.some((field) => !arraysEqual(roleDrafts[field], selected[field]))
    );
  }, [selected, shortDescriptionDraft, longDescriptionDraft, criticalityDraft, statusDraft, colorDraft, iconDraft, tagsDraft, roleDrafts]);

  // Colors already assigned to some block, most-used first -- lets a new
  // pick reuse what's already out there instead of every block drifting to
  // its own one-off shade. Not "recently clicked": a color someone picked
  // once and never saved anywhere shouldn't show up here.
  const usedColors = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of items) {
      if (item.color) counts.set(item.color, (counts.get(item.color) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([color]) => color).slice(0, 8);
  }, [items]);

  function applyItemPatch(itemId: string, patch: Partial<FabricCatalogItem>) {
    setItems((prev) => prev.map((i) => (i.item_id === itemId ? { ...i, ...patch } : i)));
  }

  async function handleToggleFavorite(item: FabricCatalogItem) {
    setActionError(null);
    try {
      const result = await setFabricFavorite(item.item_id, !item.is_favorite);
      applyItemPatch(item.item_id, result);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "No se pudo actualizar el favorito.");
    }
  }

  async function handleToggleHidden(item: FabricCatalogItem) {
    setActionError(null);
    try {
      const result = await setFabricHidden(item.item_id, !item.is_hidden);
      applyItemPatch(item.item_id, result);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "No se pudo actualizar la visibilidad.");
    }
  }

  async function handleCanvasAddRelationship(ownerId: string, type: FabricRelationshipType, targetId: string) {
    setCanvasError(null);
    try {
      const updated = await addFabricRelationship(ownerId, type, targetId);
      applyItemPatch(ownerId, updated);
    } catch (err) {
      setCanvasError(err instanceof ApiError ? err.message : "No se pudo guardar la relación.");
    }
  }

  async function handleCanvasRemoveRelationship(ownerId: string, type: FabricRelationshipType, targetId: string) {
    setCanvasError(null);
    try {
      const updated = await removeFabricRelationship(ownerId, type, targetId);
      applyItemPatch(ownerId, updated);
    } catch (err) {
      setCanvasError(err instanceof ApiError ? err.message : "No se pudo quitar la relación.");
    }
  }

  async function handleCanvasPositionsChange(positions: Record<string, FabricCanvasPosition>) {
    if (!selected) return;
    try {
      await setFabricCanvasPositions(selected.item_id, positions);
      applyItemPatch(selected.item_id, { canvas_positions: positions });
    } catch (err) {
      setCanvasError(err instanceof ApiError ? err.message : "No se pudo guardar la posición.");
    }
  }

  async function handlePreview(itemId?: string) {
    const targetId = itemId ?? selected?.item_id;
    if (!targetId) return;
    setPreviewItemId(targetId);
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewData(null);
    try {
      const result = await fetchFabricTablePreview(targetId);
      setPreviewData(result);
    } catch (err) {
      setPreviewError(err instanceof ApiError ? err.message : "No se pudo previsualizar la tabla.");
    } finally {
      setPreviewLoading(false);
    }
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
        data_owner: roleDrafts.data_owner,
        data_steward: roleDrafts.data_steward,
        data_custodian: roleDrafts.data_custodian,
        data_consumer: roleDrafts.data_consumer,
        criticality: criticalityDraft,
        status: statusDraft,
        tags: tagsDraft,
        color: colorDraft,
        icon: iconDraft,
        // Relationships are edited (and saved immediately) from the
        // relationship canvas now, not this form -- resend the current
        // value so this save never wipes them out.
        relationships: selected.relationships,
      });
      applyItemPatch(selected.item_id, updated);
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

  const appearanceIcon = iconDraft ? fabricIconFor(iconDraft) : null;
  const AppearanceIcon = appearanceIcon;

  return (
    <div className={styles.wrapper}>
      <div className={styles.layout}>
        <FabricCatalogBrowser
          items={items}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onToggleFavorite={(item) => void handleToggleFavorite(item)}
          onToggleHidden={(item) => void handleToggleHidden(item)}
          actionError={actionError}
          typeIcons={typeIcons}
          headerExtra={
            canEdit && (
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
            )
          }
        />

        <div className={styles.detailColumn}>
          {selected && (
            <div className={`${formStyles.card} ${styles.detailCard} print-area`}>
              <div className={styles.detailHead}>
                <strong>{selected.name}</strong>
                <span className={styles.blockSubtitle}>{selected.type}</span>
                {canEdit && (
                  <>
                    <button
                      type="button"
                      className={`${selected.is_favorite ? styles.headToggleOn : styles.headToggle} no-print`}
                      onClick={() => void handleToggleFavorite(selected)}
                    >
                      <Star size={13} fill={selected.is_favorite ? "currentColor" : "none"} /> Favorito
                    </button>
                    <button
                      type="button"
                      className={`${selected.is_hidden ? styles.headToggleOn : styles.headToggle} no-print`}
                      onClick={() => void handleToggleHidden(selected)}
                    >
                      {selected.is_hidden ? <EyeOff size={13} /> : <Eye size={13} />}
                      {selected.is_hidden ? "Oculto" : "Visible"}
                    </button>
                  </>
                )}
                <button type="button" className={`${styles.headToggle} no-print`} onClick={() => window.print()}>
                  <Printer size={13} /> Imprimir
                </button>
                {selected.item_id.startsWith(LAKEHOUSE_TABLE_ID_PREFIX) && (
                  <button type="button" className={`${styles.headToggle} no-print`} onClick={() => void handlePreview()}>
                    <Table2 size={13} /> Vista previa
                  </button>
                )}
                {selected.is_custom && canEdit && (
                  <button
                    type="button"
                    className={`${styles.deleteCustomButton} no-print`}
                    onClick={() => setConfirmDeleteCustomOpen(true)}
                  >
                    <Trash2 size={13} /> Eliminar bloque
                  </button>
                )}
              </div>
              {selected.folder_path.length > 0 && (
                <p className={styles.breadcrumb}>{selected.folder_path.join(" / ")}</p>
              )}

              <div className={`${styles.printOnlySummary} print-only`}>
                {selected.short_description && <p>{selected.short_description}</p>}
                <dl className={styles.printDl}>
                  {DATA_ROLE_FIELDS.map((field) => (
                    <div key={field}>
                      <dt>{DATA_ROLE_INFO[field].label}</dt>
                      <dd>{selected[field].length > 0 ? selected[field].join(", ") : "Sin asignar"}</dd>
                    </div>
                  ))}
                  <div>
                    <dt>Criticidad</dt>
                    <dd>{selected.criticality ? CRITICALITY_LABELS[selected.criticality] : "Sin definir"}</dd>
                  </div>
                  <div>
                    <dt>Estado</dt>
                    <dd>{selected.status ? STATUS_LABELS[selected.status] : "Sin definir"}</dd>
                  </div>
                  <div>
                    <dt>Etiquetas</dt>
                    <dd>{selected.tags.length > 0 ? selected.tags.join(", ") : "Sin etiquetas"}</dd>
                  </div>
                </dl>
                <h4>Descripción detallada</h4>
                <div
                  dangerouslySetInnerHTML={{
                    __html: renderMarkdown(selected.long_description_markdown) || "<p><em>Vacío.</em></p>",
                  }}
                />
                {selected.reviewed_at && (
                  <p>
                    Última revisión: {selected.reviewed_by} · {new Date(selected.reviewed_at).toLocaleString("es-ES")}
                  </p>
                )}
              </div>

              <div className={styles.fieldsGrid}>
                <div className={styles.generalColumn}>
                  <div className={`${formStyles.field} no-print`}>
                    <label htmlFor="fc_short_description">Descripción breve</label>
                    <input
                      id="fc_short_description"
                      type="text"
                      value={shortDescriptionDraft}
                      onChange={(e) => setShortDescriptionDraft(e.target.value)}
                      disabled={!canEdit}
                    />
                  </div>

                  <div className={`${styles.roleGrid} no-print`}>
                    {DATA_ROLE_FIELDS.map((field) => {
                      const info = DATA_ROLE_INFO[field];
                      return (
                        <div key={field} className={styles.compactField}>
                          <span className={styles.compactLabel} title={info.hint}>
                            {info.label}
                          </span>
                          <FreeTagInput
                            id={`fc_${field}`}
                            selected={roleDrafts[field]}
                            onChange={(next) => setRoleDrafts((prev) => ({ ...prev, [field]: next }))}
                            placeholder="+ Añadir…"
                            emptyHint="Sin asignar"
                          />
                        </div>
                      );
                    })}
                  </div>

                  <div className={`${styles.compactField} no-print`}>
                    <span className={styles.compactLabel}>Etiquetas</span>
                    <FreeTagInput
                      id="fc_tags"
                      selected={tagsDraft}
                      onChange={setTagsDraft}
                      placeholder="+ Añadir etiqueta…"
                      emptyHint="Sin etiquetas"
                    />
                  </div>

                  <div className={`${styles.fieldRow} no-print`}>
                    <div className={styles.compactField}>
                      <label className={styles.compactLabel} htmlFor="fc_criticality">
                        Criticidad
                      </label>
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
                    <div className={styles.compactField}>
                      <label className={styles.compactLabel} htmlFor="fc_status">
                        Estado
                      </label>
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
                    <div className={styles.compactField} ref={appearanceRef}>
                      <span className={styles.compactLabel}>Apariencia</span>
                      <div className={styles.appearanceWrap}>
                        <button
                          type="button"
                          className={styles.appearancePreview}
                          onClick={() => setAppearanceOpen((v) => !v)}
                          disabled={!canEdit}
                        >
                          {AppearanceIcon ? <AppearanceIcon size={14} /> : <Palette size={14} />}
                          <span className={styles.appearanceSwatch} style={{ background: colorDraft || "transparent" }} />
                          Editar
                        </button>
                        {appearanceOpen && (
                          <div className={styles.appearancePopover}>
                            <div className={styles.iconGrid}>
                              {FABRIC_ICON_OPTIONS.map(({ key, label, Icon }) => (
                                <button
                                  key={key}
                                  type="button"
                                  title={label}
                                  className={iconDraft === key ? styles.iconActive : styles.iconOption}
                                  onClick={() => setIconDraft(key)}
                                >
                                  <Icon size={14} />
                                </button>
                              ))}
                              {iconDraft && (
                                <button type="button" title="Quitar icono" className={styles.iconOption} onClick={() => setIconDraft("")}>
                                  <X size={14} />
                                </button>
                              )}
                            </div>
                            <div className={styles.colorPickRow}>
                              <input
                                type="color"
                                value={colorDraft || "#94a3b8"}
                                onChange={(e) => setColorDraft(e.target.value)}
                              />
                              {colorDraft && (
                                <button type="button" className={styles.relType} onClick={() => setColorDraft("")}>
                                  Quitar
                                </button>
                              )}
                            </div>
                            {usedColors.length > 0 && (
                              <div className={styles.colorPickRow}>
                                <span className={styles.compactLabel} title="Colores ya usados en otros bloques -- reutilízalos para homogeneizar">
                                  Usados:
                                </span>
                                {usedColors.map((c) => (
                                  <button
                                    key={c}
                                    type="button"
                                    className={styles.recentSwatch}
                                    style={{ background: c }}
                                    title={c}
                                    onClick={() => setColorDraft(c)}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className={formStyles.field}>
                    <div className={styles.detailHead}>
                      <label style={{ marginBottom: 0 }}>Relaciones</label>
                      {canEdit && (
                        <button
                          type="button"
                          className={`${styles.relType} no-print`}
                          onClick={() => setRelationshipModalOpen(true)}
                        >
                          Editar relaciones
                        </button>
                      )}
                    </div>
                    <div className={styles.diagramWrap}>
                      <FabricRelationshipCanvas
                        items={items}
                        centerId={selected.item_id}
                        canvasPositions={selected.canvas_positions}
                        interactive={false}
                        height={200}
                        testId="fabric-catalog-relationship-preview"
                      />
                    </div>
                  </div>

                </div>

                <div className={`${styles.longDescColumn} no-print`}>
                  <div className={styles.detailHead}>
                    <div className={styles.detailTabBar}>
                      <button
                        type="button"
                        className={detailTab === "descripcion" ? styles.detailTabActive : styles.detailTab}
                        onClick={() => setDetailTab("descripcion")}
                      >
                        Descripción detallada
                      </button>
                      <button
                        type="button"
                        className={detailTab === "modelo" ? styles.detailTabActive : styles.detailTab}
                        onClick={() => {
                          setDetailTab("modelo");
                          setHasOpenedModeloTab(true);
                        }}
                      >
                        Modelo semántico
                      </button>
                    </div>
                    {detailTab === "descripcion" && (
                      <div className={styles.longDescActions}>
                        <button
                          type="button"
                          className={styles.relType}
                          onClick={() => setLongDescriptionView((v) => (v === "editar" ? "vista previa" : "editar"))}
                        >
                          {longDescriptionView === "editar" ? "Ver vista previa" : "Volver a editar"}
                        </button>
                        {canEdit && (
                          <button
                            type="button"
                            className={formStyles.submit}
                            onClick={() => void handleSave()}
                            disabled={isSaving || !isDirty}
                          >
                            {isSaving ? "Guardando…" : "Guardar"}
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  <div className={styles.longDescBody} hidden={detailTab !== "descripcion"}>
                    {(saveSuccess || saveError) && (
                      <div>
                        {saveSuccess && <div className={formStyles.successBanner}>{saveSuccess}</div>}
                        {saveError && <div className={formStyles.errorBanner}>{saveError}</div>}
                      </div>
                    )}
                    {longDescriptionView === "editar" ? (
                      <textarea
                        id="fc_long_description"
                        className={styles.mdTextarea}
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

                  {/* Mounted once (on first "Modelo semántico" click) and kept mounted for the
                      rest of this item's selection, just hidden via CSS -- see hasOpenedModeloTab. */}
                  {hasOpenedModeloTab && (
                    <div hidden={detailTab !== "modelo"}>
                      <FabricSemanticModelSection itemId={selected.item_id} itemName={selected.name} canEdit={canEdit} />
                    </div>
                  )}
                </div>
              </div>

              {selected.reviewed_at && (
                <p className={`${styles.reviewedHint} no-print`}>
                  Última revisión: {selected.reviewed_by} · {new Date(selected.reviewed_at).toLocaleString("es-ES")}
                </p>
              )}

              <Modal
                open={relationshipModalOpen}
                size="large"
                eyebrow="Gobernanza de datos"
                title={`Relaciones de ${selected.name}`}
                subtitle="Arrastra desde el borde de un bloque a otro para conectarlos. Añade bloques sueltos con “Añadir bloque” y luego conéctalos."
                onClose={() => setRelationshipModalOpen(false)}
              >
                {relationshipModalOpen && (
                  // Only mounted once the dialog is actually open -- a
                  // <dialog> without the open attribute is display:none,
                  // so mounting react-flow inside it earlier would measure
                  // a zero-size container and fitView would zoom to
                  // nothing (real bug, caught live: both blocks rendered
                  // as barely-visible slivers in the corner).
                  <FabricRelationshipCanvas
                    items={items}
                    centerId={selected.item_id}
                    canvasPositions={selected.canvas_positions}
                    interactive
                    height="65vh"
                    onAddRelationship={(ownerId, type, targetId) => void handleCanvasAddRelationship(ownerId, type, targetId)}
                    onRemoveRelationship={(ownerId, type, targetId) =>
                      void handleCanvasRemoveRelationship(ownerId, type, targetId)
                    }
                    onPositionsChange={(positions) => void handleCanvasPositionsChange(positions)}
                    onPreviewItem={(itemId) => void handlePreview(itemId)}
                    testId="fabric-catalog-relationship-modal-canvas"
                  />
                )}
                {canvasError && <div className={formStyles.errorBanner}>{canvasError}</div>}
              </Modal>

              <Modal
                open={previewOpen}
                size="large"
                eyebrow="Gobernanza de datos"
                title={`Vista previa de ${items.find((i) => i.item_id === previewItemId)?.name ?? ""}`}
                subtitle="SELECT TOP 10 * -- solo para ver la estructura, no es una exportación de datos."
                onClose={() => setPreviewOpen(false)}
              >
                {previewLoading && <p>Consultando la tabla…</p>}
                {previewError && <div className={formStyles.errorBanner}>{previewError}</div>}
                {previewData && (
                  <div className={styles.previewTableWrap}>
                    <table className={styles.previewTable}>
                      <thead>
                        <tr>
                          {previewData.columns.map((col) => (
                            <th key={col}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {previewData.rows.map((row, i) => (
                          <tr key={i}>
                            {row.map((value, j) => (
                              <td key={j}>{value}</td>
                            ))}
                          </tr>
                        ))}
                        {previewData.rows.length === 0 && (
                          <tr>
                            <td colSpan={previewData.columns.length || 1}>La tabla no tiene filas.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </Modal>
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
