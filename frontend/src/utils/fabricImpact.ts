import type { FabricCatalogItem } from "../api/fabricCatalog";

/** Directed producer -> consumer adjacency over the WHOLE catalog, used for
 * impact analysis (what does this depend on / what would a change to it
 * affect). A relationship always points from whoever produces/triggers to
 * whoever consumes/is triggered, regardless of which of the two items
 * declared it: "writes_to" is declared forward (owner -> target);
 * "reads_from" and "triggered_by" are declared backward (target -> owner). */
export function buildImpactGraph(items: FabricCatalogItem[]): {
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

export function reachable(startId: string, adjacency: Map<string, Set<string>>): Set<string> {
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

export function computeImpact(
  items: FabricCatalogItem[],
  itemId: string,
): { upstream: FabricCatalogItem[]; downstream: FabricCatalogItem[] } {
  const { forward, backward } = buildImpactGraph(items);
  const byId = new Map(items.map((i) => [i.item_id, i]));
  const upstreamIds = reachable(itemId, backward);
  const downstreamIds = reachable(itemId, forward);
  return {
    upstream: [...upstreamIds].map((id) => byId.get(id)).filter((i): i is FabricCatalogItem => !!i),
    downstream: [...downstreamIds].map((id) => byId.get(id)).filter((i): i is FabricCatalogItem => !!i),
  };
}
