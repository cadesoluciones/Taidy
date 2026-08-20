import { apiGet, apiPatch } from "./client";

export type FabricRelationshipType = "reads_from" | "writes_to" | "triggered_by";
export type FabricCriticality = "" | "baja" | "media" | "alta";
export type FabricStatus = "" | "activo" | "en_desuso" | "deprecado";

export interface FabricRelationship {
  type: FabricRelationshipType;
  target_item_id: string;
}

export interface FabricCatalogItem {
  item_id: string;
  name: string;
  type: string; // Notebook | DataPipeline | Lakehouse | Warehouse | Report | ...
  folder_path: string[];
  short_description: string;
  long_description_markdown: string;
  owners: string[];
  criticality: FabricCriticality;
  status: FabricStatus;
  tags: string[];
  relationships: FabricRelationship[];
  reviewed_by: string;
  reviewed_at: string;
}

export interface FabricCatalogItemUpdate {
  short_description: string;
  long_description_markdown: string;
  owners: string[];
  criticality: FabricCriticality;
  status: FabricStatus;
  tags: string[];
  relationships: FabricRelationship[];
}

export function fetchFabricCatalog(): Promise<{ items: FabricCatalogItem[] }> {
  return apiGet<{ items: FabricCatalogItem[] }>("/fabric-catalog/items");
}

export function updateFabricCatalogItem(
  itemId: string,
  update: FabricCatalogItemUpdate,
): Promise<Omit<FabricCatalogItem, "item_id" | "name" | "type" | "folder_path">> {
  return apiPatch(`/fabric-catalog/items/${encodeURIComponent(itemId)}`, update);
}
