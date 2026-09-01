import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";

export type FabricRelationshipType = "reads_from" | "writes_to" | "triggered_by" | "generates" | "updates";

/** A relationship is always stored in the literal order it was drawn
 * (owner = the block dragged FROM, target = the block dropped ON) -- these
 * are the types whose own wording runs the OTHER way regardless: "Se
 * lanza tras" ("launched after") describes the owner as coming after the
 * target, so the target is what actually triggers it and is upstream, not
 * the owner. Every other type reads at face value from the owner's
 * perspective (owner writes/generates/updates/is-read-at the target), so
 * the owner is upstream for those. Shared between the relationship-editor
 * canvas and the impact-analysis graph so the two can never disagree
 * about which end of a relationship is upstream.*/
export const BACKWARD_RELATIONSHIP_TYPES: ReadonlySet<FabricRelationshipType> = new Set(["triggered_by"]);
export type FabricCriticality = "" | "baja" | "media" | "alta";
export type FabricStatus = "" | "activo" | "en_desuso" | "deprecado";
export type DataRoleField = "data_owner" | "data_steward" | "data_custodian" | "data_consumer";

export const DATA_ROLE_FIELDS: DataRoleField[] = ["data_owner", "data_steward", "data_custodian", "data_consumer"];

export interface FabricRelationship {
  type: FabricRelationshipType;
  target_item_id: string;
}

export interface FabricCanvasPosition {
  x: number;
  y: number;
}

export interface FabricCatalogItem {
  item_id: string;
  name: string;
  type: string; // Notebook | DataPipeline | Lakehouse | Warehouse | Report | Tabla | ...
  folder_path: string[];
  short_description: string;
  long_description_markdown: string;
  data_owner: string[];
  data_steward: string[];
  data_custodian: string[];
  data_consumer: string[];
  criticality: FabricCriticality;
  status: FabricStatus;
  tags: string[];
  relationships: FabricRelationship[];
  reviewed_by: string;
  reviewed_at: string;
  /** true for a manually-declared block with no live upstream backing --
   * see webapp/fabric_catalog.py's create_custom_item(). */
  is_custom: boolean;
  color: string; // hex, e.g. "#3b82f6", or "" for the default styling
  icon: string; // a key from utils/fabricIcons.ts, or "" for the default icon
  /** Positions of OTHER items as seen on THIS item's own relationship
   * canvas -- keyed by the other item's id, never shared across items. */
  canvas_positions: Record<string, FabricCanvasPosition>;
  is_favorite: boolean;
  /** "online": Fabric returned this item on the last catalog fetch.
   * "offline": it didn't (an outage, or its capacity/license lapsed) -- this
   * is the last-known copy instead of the item just disappearing. Always
   * "online" for BC/HubSpot/Factorial/custom items -- they're static
   * config, never Fabric-discovered. */
  connection_status: "online" | "offline";
  /** ISO timestamp of the last time this item was actually seen live --
   * "" while connection_status is "online" (it's current, no need to say
   * when). */
  last_synced_at: string;
  is_hidden: boolean;
}

export interface FabricCatalogItemUpdate {
  short_description: string;
  long_description_markdown: string;
  data_owner: string[];
  data_steward: string[];
  data_custodian: string[];
  data_consumer: string[];
  criticality: FabricCriticality;
  status: FabricStatus;
  tags: string[];
  relationships: FabricRelationship[];
  color: string;
  icon: string;
}

export function fetchFabricCatalog(): Promise<{ items: FabricCatalogItem[] }> {
  return apiGet<{ items: FabricCatalogItem[] }>("/fabric-catalog/items");
}

/** Forgets a "sin conexión" item's local copy -- never touches Fabric
 * itself, so a real item that's still there just reappears if Fabric lists
 * it live again later. 400 for anything currently online, or a BC/HubSpot/
 * Factorial/custom item (always online, doesn't apply). */
export function deleteOfflineItem(itemId: string): Promise<void> {
  return apiDelete(`/fabric-catalog/items/${encodeURIComponent(itemId)}`);
}

export function updateFabricCatalogItem(
  itemId: string,
  update: FabricCatalogItemUpdate,
): Promise<
  Omit<FabricCatalogItem, "item_id" | "name" | "type" | "folder_path" | "is_custom" | "connection_status" | "last_synced_at">
> {
  return apiPatch(`/fabric-catalog/items/${encodeURIComponent(itemId)}`, update);
}

export function createCustomFabricItem(name: string, type: string): Promise<FabricCatalogItem> {
  return apiPost<FabricCatalogItem>("/fabric-catalog/custom-items", { name, type });
}

export function deleteCustomFabricItem(itemId: string): Promise<void> {
  return apiDelete<void>(`/fabric-catalog/custom-items/${encodeURIComponent(itemId)}`);
}

type RelationshipSaveResult = Pick<FabricCatalogItem, "relationships" | "reviewed_by" | "reviewed_at">;

/** Used by the free-form relationship canvas: saves immediately onto
 * whichever item owns the new connection, independent of any in-progress
 * edit of that item's other fields. */
export function addFabricRelationship(
  ownerItemId: string,
  type: FabricRelationshipType,
  targetItemId: string,
): Promise<RelationshipSaveResult> {
  return apiPost(`/fabric-catalog/items/${encodeURIComponent(ownerItemId)}/relationships`, {
    type,
    target_item_id: targetItemId,
  });
}

export function removeFabricRelationship(
  ownerItemId: string,
  type: FabricRelationshipType,
  targetItemId: string,
): Promise<RelationshipSaveResult> {
  const params = new URLSearchParams({ type, target_item_id: targetItemId });
  return apiDelete(`/fabric-catalog/items/${encodeURIComponent(ownerItemId)}/relationships?${params.toString()}`);
}

export function setFabricCanvasPositions(
  itemId: string,
  positions: Record<string, FabricCanvasPosition>,
): Promise<{ canvas_positions: Record<string, FabricCanvasPosition> }> {
  return apiPut(`/fabric-catalog/items/${encodeURIComponent(itemId)}/canvas-positions`, { positions });
}

type FlagsResult = Pick<FabricCatalogItem, "is_favorite" | "is_hidden">;

export function setFabricFavorite(itemId: string, isFavorite: boolean): Promise<FlagsResult> {
  return apiPut(`/fabric-catalog/items/${encodeURIComponent(itemId)}/favorite`, { is_favorite: isFavorite });
}

export function setFabricHidden(itemId: string, isHidden: boolean): Promise<FlagsResult> {
  return apiPut(`/fabric-catalog/items/${encodeURIComponent(itemId)}/hidden`, { is_hidden: isHidden });
}

/** Same id prefix webapp/fabric_catalog.py builds for a Lakehouse's own
 * tables (see LAKEHOUSE_TABLE_ID_PREFIX there) -- only these are backed by
 * a real SQL-queryable table, so only they get a structure-preview button. */
export const LAKEHOUSE_TABLE_ID_PREFIX = "lakehouse-table:";

export interface FabricTablePreview {
  columns: string[];
  rows: string[][];
}

/** `SELECT TOP 10 *` against the real table a "lakehouse-table:..." item
 * stands for -- just to see its columns and a few sample rows. */
export function fetchFabricTablePreview(itemId: string): Promise<FabricTablePreview> {
  return apiGet(`/fabric-catalog/items/${encodeURIComponent(itemId)}/preview`);
}

/** Data types selectable for a manually-defined (non-Lakehouse) column --
 * TMDL's own vocabulary, distinct from the DAX DATATABLE() one used behind
 * the scenes to give the table a valid (empty) partition. */
export const MANUAL_DATA_TYPES = ["string", "int64", "double", "boolean", "dateTime"] as const;
export type ManualDataType = (typeof MANUAL_DATA_TYPES)[number];

export interface ManualColumn {
  name: string;
  data_type: string;
}

export interface SemanticModelColumn {
  name: string;
  description: string;
  in_source: boolean;
  data_type: string;
}

export interface SemanticModelState {
  linked: boolean;
  model_item_id: string;
  model_name: string;
  columns: SemanticModelColumn[];
  /** Real source-table columns the model doesn't have yet -- empty when
   * nothing's missing, or (when not linked) every column of the table.
   * Always empty for a manual (has_real_source: false) model. */
  missing_columns: string[];
  /** false for BC/HubSpot/Factorial/custom items: no live table backs the
   * model, columns are defined by hand as a plain data dictionary. */
  has_real_source: boolean;
}

export function fetchSemanticModelState(itemId: string): Promise<SemanticModelState> {
  return apiGet(`/fabric-catalog/items/${encodeURIComponent(itemId)}/semantic-model`);
}

/** Creates a new semantic model for this item. For a real Lakehouse table,
 * columns are auto-detected from its schema and itemName/columns are
 * ignored. Otherwise it's a manual data dictionary -- itemName and at
 * least one column are required. */
export function createSemanticModel(
  itemId: string,
  itemName: string = "",
  columns: ManualColumn[] = []
): Promise<SemanticModelState> {
  return apiPost(`/fabric-catalog/items/${encodeURIComponent(itemId)}/semantic-model`, {
    item_name: itemName,
    columns,
  });
}

export function updateSemanticModelDescriptions(
  itemId: string,
  descriptions: Record<string, string>
): Promise<SemanticModelState> {
  return apiPatch(`/fabric-catalog/items/${encodeURIComponent(itemId)}/semantic-model`, { descriptions });
}

/** Adds any column the real table has that the model doesn't yet -- schema
 * drift auto-detection, see missing_columns. Lakehouse tables only. */
export function syncSemanticModelColumns(itemId: string): Promise<SemanticModelState> {
  return apiPost(`/fabric-catalog/items/${encodeURIComponent(itemId)}/semantic-model/sync-columns`);
}

/** Replaces the full column list of a manual (non-Lakehouse) semantic
 * model -- used to add or remove columns by hand. Existing descriptions
 * are preserved by column name. */
export function setManualSemanticModelColumns(
  itemId: string,
  columns: ManualColumn[]
): Promise<SemanticModelState> {
  return apiPut(`/fabric-catalog/items/${encodeURIComponent(itemId)}/semantic-model/columns`, { columns });
}

/** The default icon key (see FABRIC_ICON_OPTIONS) shown for each catalog
 * item type when an item hasn't had one set by hand -- built-in defaults
 * plus whatever an admin overrode in Configuración. */
export function fetchTypeIcons(): Promise<{ icons: Record<string, string> }> {
  return apiGet("/fabric-catalog/type-icons");
}

/** icon: "" clears an override, falling back to the built-in default (or
 * none) for that type. */
export function setTypeIcon(type: string, icon: string): Promise<{ icons: Record<string, string> }> {
  return apiPut("/fabric-catalog/type-icons", { type, icon });
}
