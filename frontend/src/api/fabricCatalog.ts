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

export function updateFabricCatalogItem(
  itemId: string,
  update: FabricCatalogItemUpdate,
): Promise<Omit<FabricCatalogItem, "item_id" | "name" | "type" | "folder_path" | "is_custom">> {
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
