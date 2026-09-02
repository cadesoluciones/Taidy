import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";

import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
  type OnConnect,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Plus, Table2, X } from "lucide-react";

import {
  BACKWARD_RELATIONSHIP_TYPES,
  LAKEHOUSE_TABLE_ID_PREFIX,
  type FabricCatalogItem,
  type FabricCanvasPosition,
  type FabricRelationshipType,
} from "../api/fabricCatalog";
import { fabricIconFor } from "../utils/fabricIcons";
import styles from "./FabricRelationshipCanvas.module.css";

export const RELATIONSHIP_LABELS: Record<FabricRelationshipType, string> = {
  reads_from: "Se lee en",
  writes_to: "Escribe en",
  generates: "Genera",
  updates: "Actualiza",
  triggered_by: "Se lanza tras",
};

type BlockNodeData = Record<string, unknown> & {
  label: string;
  typeLabel: string;
  color: string;
  icon: string;
  isCenter: boolean;
  canRemove: boolean;
  onRemove?: (id: string) => void;
  canPreview: boolean;
  onPreview?: ((id: string) => void) | undefined;
};
type BlockFlowNode = Node<BlockNodeData, "block">;

function BlockNode({ id, data, selected }: NodeProps<BlockFlowNode>) {
  const Icon = data.icon ? fabricIconFor(data.icon) : null;
  return (
    <div
      className={styles.node}
      data-selected={selected || undefined}
      data-center={data.isCenter || undefined}
      style={data.color ? { borderColor: data.color } : undefined}
    >
      <Handle type="target" position={Position.Top} className={styles.handle} />
      {data.canRemove && (
        <button
          type="button"
          className={styles.removeExtra}
          aria-label="Quitar bloque"
          title="Quitar este bloque del diagrama (elimina sus relaciones aquí mostradas)"
          onClick={(e) => {
            e.stopPropagation();
            data.onRemove?.(id);
          }}
        >
          <X size={11} />
        </button>
      )}
      <div className={styles.nodeHead}>
        {Icon && <Icon size={15} />}
        <span className={styles.nodeLabel}>{data.label}</span>
      </div>
      <div className={styles.nodeType}>{data.typeLabel}</div>
      {data.canPreview && (
        <button
          type="button"
          className={styles.previewButton}
          aria-label="Vista previa de la tabla"
          title="Vista previa de la tabla (SELECT TOP 10)"
          onClick={(e) => {
            e.stopPropagation();
            data.onPreview?.(id);
          }}
        >
          <Table2 size={11} />
        </button>
      )}
      <Handle type="source" position={Position.Bottom} className={styles.handle} />
    </div>
  );
}

const nodeTypes = { block: BlockNode };

/** `fitView` (the boolean prop) fits once at mount, but on the SAME tick --
 * before react-flow has measured the nodes' real rendered size, since
 * they're never given explicit width/height. Deferring one animation frame
 * covers that for the common case (the container is already visible when
 * this mounts). It does NOT cover the relationship-editor modal: its
 * <dialog> starts as `display: none` until Modal's own effect calls
 * `showModal()` on it, and that effect runs AFTER this component's (React
 * fires child effects before parent effects) -- but a `display:none`
 * ancestor still means the canvas div has no box at all the moment THIS
 * effect's rAF fires, one frame later, regardless of ordering. A single
 * fixed delay can't reliably outlast an unknown dialog-open timing, so
 * instead a ResizeObserver on the actual canvas container reacts to
 * whatever moment it gets its first real (non-zero) box -- that's the
 * exact event we care about, not a guessed frame count. Disconnects after
 * its first callback so it doesn't keep re-snapping the view on later,
 * legitimate window resizes while someone is mid-edit. */
function FitViewOnNodesChange({ signature, containerRef }: { signature: string; containerRef: RefObject<HTMLDivElement | null> }) {
  const { fitView } = useReactFlow();

  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      fitView({ padding: 0.3 });
    });

    const el = containerRef.current;
    let observer: ResizeObserver | null = null;
    if (el) {
      observer = new ResizeObserver(() => {
        fitView({ padding: 0.3 });
        observer?.disconnect();
      });
      observer.observe(el);
    }

    return () => {
      cancelAnimationFrame(raf);
      observer?.disconnect();
    };
  }, [signature, fitView, containerRef]);

  return null;
}

const ROW_GAP_Y = 100;
const COL_GAP_X = 180;
// Matches .node's fixed CSS width and its typical rendered height (icon +
// name line, type line, padding). react-flow needs a width/height on the
// node object itself to compute fitView's bounding box on the very first
// render -- without it, it has to wait for a ResizeObserver measurement
// that may not have landed yet, and fitView on that unmeasured box was
// exactly the "existing blocks end up displaced" bug reported live
// (worst with a single, relationship-less node, where an empty/zero-size
// bounding box has nothing else to average out against).
const NODE_WIDTH = 160;
const NODE_HEIGHT = 64;

interface EdgeInfo {
  id: string;
  producer: string;
  consumer: string;
  ownerId: string;
  type: FabricRelationshipType;
  targetId: string;
}

/** Gathers the centre's local neighborhood (signed depth: negative = what
 * it depends on, above; positive = what depends on it, below) and every
 * relationship whose both ends land in that neighborhood -- including ones
 * between two OTHER items, not just ones touching the centre. Mirrors the
 * hop-limited gathering the compact preview used before this rewrite, but
 * tracks a signed depth (for vertical placement) instead of an unsigned
 * hop count, and keeps full edge identity (not just a label) since edges
 * are now independently addressable (click-to-remove, drag-to-connect). */
function buildNeighborhood(
  items: FabricCatalogItem[],
  centerId: string,
  extraNodeIds: string[],
  hops: number,
): { depth: Map<string, number>; edges: EdgeInfo[] } {
  const forward = new Map<string, Set<string>>();
  const backward = new Map<string, Set<string>>();
  const edgeInfoByPair = new Map<string, EdgeInfo[]>();

  function addEdge(producer: string, consumer: string, info: EdgeInfo) {
    if (!forward.has(producer)) forward.set(producer, new Set());
    forward.get(producer)!.add(consumer);
    if (!backward.has(consumer)) backward.set(consumer, new Set());
    backward.get(consumer)!.add(producer);
    const key = `${producer} ${consumer}`;
    if (!edgeInfoByPair.has(key)) edgeInfoByPair.set(key, []);
    edgeInfoByPair.get(key)!.push(info);
  }

  for (const item of items) {
    for (const rel of item.relationships) {
      const info: EdgeInfo = {
        id: `${item.item_id}|${rel.type}|${rel.target_item_id}`,
        producer: "",
        consumer: "",
        ownerId: item.item_id,
        type: rel.type,
        targetId: rel.target_item_id,
      };
      if (BACKWARD_RELATIONSHIP_TYPES.has(rel.type)) {
        info.producer = rel.target_item_id;
        info.consumer = item.item_id;
      } else {
        info.producer = item.item_id;
        info.consumer = rel.target_item_id;
      }
      addEdge(info.producer, info.consumer, info);
    }
  }

  const depth = new Map<string, number>([[centerId, 0]]);
  let frontier = [centerId];
  for (let hop = 0; hop < hops && frontier.length > 0; hop++) {
    const next: string[] = [];
    for (const id of frontier) {
      const d = depth.get(id) ?? 0;
      for (const consumer of forward.get(id) ?? []) {
        if (!depth.has(consumer)) {
          depth.set(consumer, d + 1);
          next.push(consumer);
        }
      }
      for (const producer of backward.get(id) ?? []) {
        if (!depth.has(producer)) {
          depth.set(producer, d - 1);
          next.push(producer);
        }
      }
    }
    frontier = next;
  }

  for (const id of extraNodeIds) {
    if (!depth.has(id)) depth.set(id, 1);
  }

  const edges: EdgeInfo[] = [];
  for (const infos of edgeInfoByPair.values()) {
    for (const info of infos) {
      if (depth.has(info.producer) && depth.has(info.consumer)) edges.push(info);
    }
  }

  return { depth, edges };
}

function layoutVertical(depth: Map<string, number>): Map<string, { x: number; y: number }> {
  const rows = new Map<number, string[]>();
  for (const [id, d] of depth) {
    if (!rows.has(d)) rows.set(d, []);
    rows.get(d)!.push(id);
  }
  const positions = new Map<string, { x: number; y: number }>();
  for (const [d, ids] of rows) {
    const rowWidth = (ids.length - 1) * COL_GAP_X;
    ids.forEach((id, i) => {
      positions.set(id, { x: i * COL_GAP_X - rowWidth / 2, y: d * ROW_GAP_Y });
    });
  }
  return positions;
}

interface FabricRelationshipCanvasProps {
  items: FabricCatalogItem[];
  centerId: string;
  canvasPositions: Record<string, FabricCanvasPosition>;
  interactive: boolean;
  height?: number | string;
  /** Grows to fill the parent's remaining height instead of using `height`
   * -- the parent must itself be a flex container (display:flex) for this
   * to have any effect. A plain CSS `height: 100%` on this component's own
   * root div does NOT reliably resolve here even when the parent's own
   * height is definite via flex-grow (confirmed live: it measured 2px,
   * react-flow rendered nothing, not even the background dots) -- flex:1
   * chained through an ancestor that's ALSO already resolved via flex-grow
   * is the one that's actually reliable, so this stays inside that same
   * mechanism instead of switching to percentages partway down. */
  fill?: boolean;
  /** How many hops out from the center to gather (both directions), and
   * every relationship between two OTHER items that both land inside that
   * neighborhood -- not just edges touching the center. Defaults to 2 (the
   * compact preview/editor's original depth); impact analysis passes a
   * user-chosen depth up to 10 to surface the wider dependency chain. */
  hops?: number;
  /** Independent from `interactive` -- a read-only impact graph still wants
   * zoom/fit controls, just not node dragging/connecting/removing. */
  showControls?: boolean;
  onAddRelationship?: (ownerId: string, type: FabricRelationshipType, targetId: string) => void;
  onRemoveRelationship?: (ownerId: string, type: FabricRelationshipType, targetId: string) => void;
  onPositionsChange?: (positions: Record<string, FabricCanvasPosition>) => void;
  /** Shows a small preview button on any node backed by a Lakehouse table
   * (see LAKEHOUSE_TABLE_ID_PREFIX) -- omitted entirely (no button on any
   * node) where it isn't passed, e.g. the read-only impact-analysis graph. */
  onPreviewItem?: (itemId: string) => void;
  testId?: string;
}

export function FabricRelationshipCanvas({
  items,
  centerId,
  canvasPositions,
  interactive,
  height = 260,
  fill = false,
  hops = 2,
  showControls,
  onAddRelationship,
  onRemoveRelationship,
  onPositionsChange,
  onPreviewItem,
  testId,
}: FabricRelationshipCanvasProps) {
  const [extraNodeIds, setExtraNodeIds] = useState<string[]>([]);
  const [pendingConnection, setPendingConnection] = useState<{ source: string; target: string } | null>(null);
  const [addPickerOpen, setAddPickerOpen] = useState(false);
  const [addSearch, setAddSearch] = useState("");
  const canvasContainerRef = useRef<HTMLDivElement>(null);

  const itemsById = useMemo(() => new Map(items.map((i) => [i.item_id, i])), [items]);
  const { depth, edges: edgeInfos } = useMemo(
    () => buildNeighborhood(items, centerId, extraNodeIds, hops),
    [items, centerId, extraNodeIds, hops],
  );
  const autoPositions = useMemo(() => layoutVertical(depth), [depth]);
  const connectedIds = useMemo(() => {
    const set = new Set<string>();
    for (const e of edgeInfos) {
      set.add(e.producer);
      set.add(e.consumer);
    }
    return set;
  }, [edgeInfos]);

  // Removing a block that already has relationships means severing every
  // edge that connects it within this diagram -- there's no separate
  // "unlinked but present" state for a connected node, so the only way to
  // make it disappear here is to remove what ties it in. A freshly-added,
  // still-unconnected block instead just drops out of local state (nothing
  // was ever saved for it yet). Previously the remove button only showed
  // for that second case, which was the reported bug: any block that
  // already had a relationship had no way to be removed from the editor.
  const handleRemoveNode = useCallback(
    (id: string) => {
      const touching = edgeInfos.filter((e) => e.producer === id || e.consumer === id);
      if (touching.length > 0 && onRemoveRelationship) {
        for (const e of touching) onRemoveRelationship(e.ownerId, e.type, e.targetId);
      }
      setExtraNodeIds((prev) => prev.filter((x) => x !== id));
    },
    [edgeInfos, onRemoveRelationship],
  );

  const nodes: BlockFlowNode[] = useMemo(
    () =>
      [...depth.keys()].map((id) => {
        const found = itemsById.get(id);
        const isCenter = id === centerId;
        return {
          id,
          type: "block",
          position: canvasPositions[id] ?? autoPositions.get(id) ?? { x: 0, y: 0 },
          width: NODE_WIDTH,
          height: NODE_HEIGHT,
          draggable: interactive,
          connectable: interactive,
          data: {
            label: found?.name ?? id,
            typeLabel: isCenter ? `${found?.type ?? "?"} · seleccionado` : found?.type ?? "?",
            color: found?.color ?? "",
            icon: found?.icon ?? "",
            isCenter,
            canRemove: interactive && !isCenter,
            onRemove: handleRemoveNode,
            canPreview: !!onPreviewItem && !!found?.item_id.startsWith(LAKEHOUSE_TABLE_ID_PREFIX),
            onPreview: onPreviewItem,
          },
        };
      }),
    [depth, itemsById, centerId, canvasPositions, autoPositions, interactive, handleRemoveNode, onPreviewItem],
  );

  const edges: Edge[] = useMemo(
    () =>
      edgeInfos.map((e) => ({
        id: e.id,
        source: e.producer,
        target: e.consumer,
        label: RELATIONSHIP_LABELS[e.type],
        labelStyle: { fontSize: 10, fill: "var(--color-text-muted)" },
        labelBgStyle: { fill: "var(--color-bg)" },
        labelBgPadding: [3, 2] as [number, number],
      })),
    [edgeInfos],
  );

  const nodesSignature = useMemo(() => [...depth.keys()].sort().join(","), [depth]);

  function handleNodesChange(changes: NodeChange<BlockFlowNode>[]) {
    if (!onPositionsChange) return;
    for (const change of changes) {
      if (change.type === "position" && change.dragging === false && change.position) {
        // Only persist positions for blocks that actually have a
        // relationship -- a block dropped on the canvas but never
        // connected has nothing declared to save yet.
        if (extraNodeIds.includes(change.id) && !connectedIds.has(change.id)) continue;
        onPositionsChange({ ...canvasPositions, [change.id]: change.position });
      }
    }
  }

  const handleConnect: OnConnect = (connection) => {
    if (!interactive || !connection.source || !connection.target || connection.source === connection.target) return;
    setPendingConnection({ source: connection.source, target: connection.target });
  };

  function confirmConnection(type: FabricRelationshipType) {
    if (!pendingConnection || !onAddRelationship) return;
    const { source, target } = pendingConnection;
    // Always stored in literal click order -- whichever block you dragged
    // FROM is the owner, whichever you dropped ON is the target, for every
    // type. No per-type swap: each verb's own wording (see
    // RELATIONSHIP_LABELS/BACKWARD_RELATIONSHIP_TYPES above) is what
    // decides which side is upstream, not how the pair gets stored.
    onAddRelationship(source, type, target);
    setExtraNodeIds((prev) => prev.filter((id) => id !== source && id !== target));
    setPendingConnection(null);
  }

  const addCandidates = useMemo(() => {
    if (!addPickerOpen) return [];
    const q = addSearch.trim().toLowerCase();
    return items.filter((i) => {
      if (depth.has(i.item_id)) return false;
      if (!q) return true;
      return i.name.toLowerCase().includes(q) || i.type.toLowerCase().includes(q);
    });
  }, [items, addPickerOpen, addSearch, depth]);

  return (
    <div className={styles.wrapper}>
      {interactive && (
        <div className={styles.toolbar}>
          <button type="button" className={styles.addButton} onClick={() => setAddPickerOpen((v) => !v)}>
            <Plus size={13} /> Añadir bloque
          </button>
          <span className={styles.hint}>Arrastra desde el borde de un bloque a otro para conectarlos.</span>
        </div>
      )}
      {addPickerOpen && (
        <div className={styles.addPicker}>
          <input
            type="text"
            placeholder="Buscar un elemento del catálogo…"
            value={addSearch}
            onChange={(e) => setAddSearch(e.target.value)}
            className={styles.addSearch}
          />
          <div className={styles.addGrid}>
            {addCandidates.slice(0, 30).map((c) => (
              <button
                key={c.item_id}
                type="button"
                className={styles.addCandidate}
                onClick={() => {
                  setExtraNodeIds((prev) => [...prev, c.item_id]);
                  setAddPickerOpen(false);
                  setAddSearch("");
                }}
              >
                {c.name}
              </button>
            ))}
            {addCandidates.length === 0 && <p className={styles.hint}>Sin resultados.</p>}
          </div>
        </div>
      )}
      {pendingConnection && (
        <div className={styles.typePrompt}>
          <span>¿Qué tipo de relación es?</span>
          {Object.entries(RELATIONSHIP_LABELS).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={styles.typeButton}
              onClick={() => confirmConnection(key as FabricRelationshipType)}
            >
              {label}
            </button>
          ))}
          <button type="button" className={styles.typeCancel} onClick={() => setPendingConnection(null)}>
            Cancelar
          </button>
        </div>
      )}
      <div
        ref={canvasContainerRef}
        className={styles.canvas}
        style={fill ? { flex: 1, minHeight: 0 } : { height }}
        data-testid={testId}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onConnect={handleConnect}
          onNodesChange={handleNodesChange}
          onEdgeClick={(_e, edge) => {
            if (!interactive || !onRemoveRelationship) return;
            const info = edgeInfos.find((i) => i.id === edge.id);
            if (info) onRemoveRelationship(info.ownerId, info.type, info.targetId);
          }}
          nodesDraggable={interactive}
          nodesConnectable={interactive}
          elementsSelectable={interactive}
          proOptions={{ hideAttribution: true }}
          fitView
          fitViewOptions={{ padding: 0.3 }}
        >
          <Background gap={16} />
          {(showControls ?? interactive) && <Controls showInteractive={false} />}
          <FitViewOnNodesChange signature={nodesSignature} containerRef={canvasContainerRef} />
        </ReactFlow>
      </div>
    </div>
  );
}
