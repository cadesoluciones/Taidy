import { apiGet, apiPatch } from "./client";

export type FabricRelationshipType = "reads_from" | "writes_to" | "triggered_by";

export interface FabricRelationship {
  type: FabricRelationshipType;
  target_item_id: string;
}

export interface FabricCatalogItem {
  item_id: string;
  name: string;
  type: string; // Notebook | DataPipeline | Lakehouse | Warehouse | Report | ...
  folder_path: string[];
  description: string;
  relationships: FabricRelationship[];
}

export function fetchFabricCatalog(): Promise<{ items: FabricCatalogItem[] }> {
  return apiGet<{ items: FabricCatalogItem[] }>("/fabric-catalog/items");
}

export function updateFabricCatalogItem(
  itemId: string,
  description: string,
  relationships: FabricRelationship[],
): Promise<{ description: string; relationships: FabricRelationship[] }> {
  return apiPatch(`/fabric-catalog/items/${encodeURIComponent(itemId)}`, { description, relationships });
}
