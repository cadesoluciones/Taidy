import { describe, expect, it } from "vitest";

import type { FabricCatalogItem } from "../api/fabricCatalog";
import { computeImpact } from "./fabricImpact";

function item(id: string, relationships: FabricCatalogItem["relationships"] = []): FabricCatalogItem {
  return {
    item_id: id,
    name: id,
    type: "Notebook",
    folder_path: [],
    short_description: "",
    long_description_markdown: "",
    data_owner: [],
    data_steward: [],
    data_custodian: [],
    data_consumer: [],
    criticality: "",
    status: "",
    tags: [],
    relationships,
    reviewed_by: "",
    reviewed_at: "",
    is_custom: false,
    color: "",
    icon: "",
    canvas_positions: {},
    is_favorite: false,
    is_hidden: false,
  };
}

describe("computeImpact", () => {
  it("follows writes_to forward as downstream impact", () => {
    const items = [item("a", [{ type: "writes_to", target_item_id: "b" }]), item("b")];
    const impact = computeImpact(items, "a");
    expect(impact.downstream.map((i) => i.item_id)).toEqual(["b"]);
    expect(impact.upstream).toEqual([]);
  });

  it("follows reads_from backward as upstream dependency", () => {
    const items = [item("a", [{ type: "reads_from", target_item_id: "b" }]), item("b")];
    const impact = computeImpact(items, "a");
    expect(impact.upstream.map((i) => i.item_id)).toEqual(["b"]);
    expect(impact.downstream).toEqual([]);
  });

  it("finds transitive impact several hops away", () => {
    const items = [
      item("a", [{ type: "writes_to", target_item_id: "b" }]),
      item("b", [{ type: "writes_to", target_item_id: "c" }]),
      item("c"),
    ];
    const impact = computeImpact(items, "a");
    expect(new Set(impact.downstream.map((i) => i.item_id))).toEqual(new Set(["b", "c"]));
  });

  it("returns empty impact for an isolated item", () => {
    const items = [item("a")];
    const impact = computeImpact(items, "a");
    expect(impact.upstream).toEqual([]);
    expect(impact.downstream).toEqual([]);
  });
});
