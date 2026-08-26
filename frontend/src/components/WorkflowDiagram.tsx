import { useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useReactFlow,
  useStore,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
  type OnConnect,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { NEEDS_TABLES } from "../utils/actionParamGroups";
import { statusMeta } from "./statusMeta";
import styles from "./WorkflowDiagram.module.css";

/** Structural subset shared by StepDefinition (draft/saved steps) and
 * StepRun (live run steps) -- the diagram only ever needs these fields,
 * so it accepts either without the caller reshaping data. `params` is
 * optional because StepRun carries no params at all -- a run's card just
 * shows no scope/target detail line instead, which is fine since it
 * already shows richer live status there. */
export interface DiagramStep {
  id: string;
  label: string;
  action: string;
  depends_on: string[];
  trigger_rule: string;
  params?: Record<string, unknown>;
}

/** A short second line under the action label -- which tables a
 * NEEDS_TABLES block is scoped to, or which pipeline/mapping/flow a
 * single-target block launches. Returns undefined when the action has no
 * such target concept (nothing to add beyond the action label itself) or
 * when `params` wasn't supplied (run view). */
function computeDetailLabel(
  action: string,
  params: Record<string, unknown> | undefined,
  workflowNamesById: Record<string, string> | undefined,
): string | undefined {
  if (!params) return undefined;
  if (NEEDS_TABLES.has(action)) {
    const tables = params.tables as string[] | undefined;
    if (!tables || tables.length === 0) return "Todas las tablas";
    return tables.length === 1 ? tables[0] : `${tables.length} tablas`;
  }
  if (action === "run_pipeline") return (params.pipeline as string | undefined) || undefined;
  if (action === "sync_apply") return (params.mapping as string | undefined) || undefined;
  if (action === "run_workflow") {
    const id = params.workflow_id as string | undefined;
    return id ? (workflowNamesById?.[id] ?? undefined) : undefined;
  }
  return undefined;
}

type StepNodeData = Record<string, unknown> & {
  label: string;
  actionLabel: string;
  detailLabel?: string;
  status?: string;
  detail?: string | null;
  alwaysRun?: boolean;
  elapsedSeconds?: number;
  onRename?: (label: string) => void;
};

type StepFlowNode = Node<StepNodeData, "step">;

function StepNode({ data, selected }: NodeProps<StepFlowNode>) {
  const status = data.status;
  const onRename = data.onRename;
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(data.label);

  function commit() {
    setIsEditing(false);
    const trimmed = draft.trim();
    if (trimmed && trimmed !== data.label) onRename?.(trimmed);
    else setDraft(data.label);
  }

  return (
    <div className={styles.node} data-selected={selected || undefined} data-status={status ?? "none"}>
      <Handle type="target" position={Position.Left} className={styles.handle} />
      {isEditing ? (
        <input
          className={`${styles.nodeLabelInput} nodrag`}
          value={draft}
          autoFocus
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") {
              setDraft(data.label);
              setIsEditing(false);
            }
          }}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <div
          className={styles.nodeLabel}
          title={onRename ? "Doble clic para renombrar" : undefined}
          onDoubleClick={(e) => {
            if (!onRename) return;
            e.stopPropagation();
            setDraft(data.label);
            setIsEditing(true);
          }}
        >
          {data.label}
        </div>
      )}
      <div className={styles.nodeAction}>{data.actionLabel}</div>
      {data.detailLabel && <div className={styles.nodeDetail}>{data.detailLabel}</div>}
      {status && (
        <div className={styles.nodeStatus}>
          {statusMeta(status).label.toLowerCase()}
          {data.elapsedSeconds !== undefined && ` · ${data.elapsedSeconds.toFixed(0)}s`}
        </div>
      )}
      {status === "error" && data.detail && <div className={styles.nodeHint}>{data.detail}</div>}
      {data.alwaysRun && <div className={styles.nodeHint}>se lanza aunque falle una dependencia</div>}
      <Handle type="source" position={Position.Right} className={styles.handle} />
    </div>
  );
}

export interface StepTiming {
  started_at: string | null;
  finished_at: string | null;
}

/** Seconds elapsed for a step that has started -- ticks up naturally on
 * every parent re-render (WorkflowsPage polls run status every 3s) while
 * running, freezes at the real duration once finished_at lands. */
function elapsedSecondsFor(timing: StepTiming | undefined): number | undefined {
  if (!timing?.started_at) return undefined;
  const start = new Date(timing.started_at).getTime();
  const end = timing.finished_at ? new Date(timing.finished_at).getTime() : Date.now();
  return Math.max(0, (end - start) / 1000);
}

const nodeTypes = { step: StepNode };

/** React Flow's `fitView` prop only re-centers the viewport on the initial
 * mount -- adding a block, or connecting one (which can shift a node into a
 * new dependency layer, see layoutSteps()), repositions nodes without ever
 * re-fitting, so a newly-placed node/edge landing outside the viewport that
 * was fit around the ORIGINAL, smaller layout would otherwise go unseen.
 *
 * But re-fitting on *every* layout change resets the zoom/pan the user just
 * set, which is disorienting when working zoomed into one area and adding
 * an unrelated block elsewhere. So this only calls fitView when the new
 * layout actually doesn't fit inside the current viewport -- otherwise it
 * leaves the current zoom/pan alone. The very first layout (mount) is left
 * to the <ReactFlow fitView> prop, not duplicated here. */
function FitViewOnLayoutChange({ layoutSignature, nodes }: { layoutSignature: string; nodes: StepFlowNode[] }) {
  const { fitView, getViewport } = useReactFlow();
  const { width, height } = useStore((s) => ({ width: s.width, height: s.height }));
  const isFirstRun = useRef(true);

  useEffect(() => {
    if (nodes.length === 0) return;

    if (isFirstRun.current) {
      isFirstRun.current = false;
      return;
    }

    if (!width || !height) {
      fitView({ padding: 0.3 });
      return;
    }

    const { x, y, zoom } = getViewport();
    const visibleLeft = -x / zoom;
    const visibleTop = -y / zoom;
    const visibleRight = visibleLeft + width / zoom;
    const visibleBottom = visibleTop + height / zoom;

    const allNodesVisible = nodes.every(
      (n) =>
        n.position.x >= visibleLeft &&
        n.position.y >= visibleTop &&
        n.position.x + NODE_WIDTH <= visibleRight &&
        n.position.y + NODE_HEIGHT <= visibleBottom,
    );

    if (!allNodesVisible) {
      // No animation duration -- an animated re-fit leaves a window where a
      // node's on-screen position doesn't match its final, settled position
      // yet, which is exactly the kind of window a drag-to-connect gesture
      // (grabbing a handle's coordinates once, up front) can land in.
      fitView({ padding: 0.3 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutSignature]);
  return null;
}

const NODE_WIDTH = 190;
const NODE_HEIGHT = 78;
const LAYER_GAP_X = 240;
const ROW_GAP_Y = 96;

/** Layers steps left-to-right by dependency depth (0 = no dependencies),
 * so the DAG always reads in execution order regardless of how the caller
 * ordered the `steps` array -- mirrors webapp/workflows.py:to_dot()'s
 * `rankdir=LR` layout, just computed with an explicit BFS instead of
 * leaving it to Graphviz. */
function layoutSteps(steps: DiagramStep[]): Map<string, { x: number; y: number }> {
  const depth = new Map<string, number>();
  const byId = new Map(steps.map((s) => [s.id, s]));

  function depthOf(id: string, seen: Set<string>): number {
    if (depth.has(id)) return depth.get(id) as number;
    if (seen.has(id)) return 0; // cycle guard -- shouldn't happen, backend rejects cycles
    seen.add(id);
    const step = byId.get(id);
    const deps = step?.depends_on ?? [];
    const d = deps.length === 0 ? 0 : 1 + Math.max(...deps.map((dep) => depthOf(dep, seen)));
    depth.set(id, d);
    return d;
  }
  steps.forEach((s) => depthOf(s.id, new Set()));

  const rowsPerLayer = new Map<number, number>();
  const positions = new Map<string, { x: number; y: number }>();
  for (const s of steps) {
    const d = depth.get(s.id) ?? 0;
    const row = rowsPerLayer.get(d) ?? 0;
    rowsPerLayer.set(d, row + 1);
    positions.set(s.id, { x: d * LAYER_GAP_X, y: row * ROW_GAP_Y });
  }
  return positions;
}

interface WorkflowDiagramProps {
  steps: DiagramStep[];
  actionLabels: Record<string, string>;
  stepStatuses?: Record<string, string>;
  stepDetails?: Record<string, string | null>;
  stepTimings?: Record<string, StepTiming>;
  selectedStepId?: string | null;
  onSelectStep?: (id: string) => void;
  onConnectSteps?: (sourceId: string, targetId: string) => void;
  onRemoveDependency?: (sourceId: string, targetId: string) => void;
  /** Renaming inline on the node card itself (double-click) -- undefined in
   * read-only views, which is also what hides the "double-click" hint and
   * disables the double-click handler entirely. */
  onLabelChange?: (stepId: string, label: string) => void;
  /** Resolves a run_workflow block's target id to a human name for its
   * detail line -- StepDefinition/StepRun only carry the id. */
  workflowNamesById?: Record<string, string>;
  readOnly?: boolean;
  /** Manual positions (from a previous drag) that override the auto-layout
   * for the steps they cover -- lets the designer's canvas remember where
   * the user dragged a block instead of snapping it back on every render. */
  nodePositions?: Record<string, { x: number; y: number }>;
  onNodePositionChange?: (stepId: string, position: { x: number; y: number }) => void;
  /** Number (px) for the fixed-height read-only cards, or a CSS value like
   * "100%" for the designer, which sizes itself off its own container
   * instead (see WorkflowsPage.module.css's .designerCanvas). */
  height?: number | string;
  testId?: string;
}

export function WorkflowDiagram({
  steps,
  actionLabels,
  stepStatuses,
  stepDetails,
  stepTimings,
  selectedStepId,
  onSelectStep,
  onConnectSteps,
  onRemoveDependency,
  onLabelChange,
  workflowNamesById,
  readOnly = false,
  nodePositions,
  onNodePositionChange,
  height = 320,
  testId,
}: WorkflowDiagramProps) {
  const positions = useMemo(() => layoutSteps(steps), [steps]);
  const layoutSignature = useMemo(
    () =>
      [...positions.entries()]
        .map(([id, p]) => `${id}:${p.x},${p.y}`)
        .sort()
        .join("|"),
    [positions],
  );

  const nodes: StepFlowNode[] = useMemo(
    () =>
      steps.map((s) => {
        const status = stepStatuses?.[s.id];
        const detail = stepDetails?.[s.id];
        const elapsedSeconds = elapsedSecondsFor(stepTimings?.[s.id]);
        const detailLabel = computeDetailLabel(s.action, s.params, workflowNamesById);
        const data: StepNodeData = {
          label: s.label,
          actionLabel: actionLabels[s.action] ?? s.action,
          alwaysRun: s.depends_on.length > 0 && s.trigger_rule === "always",
          ...(detailLabel ? { detailLabel } : {}),
          ...(status !== undefined ? { status } : {}),
          ...(detail ? { detail } : {}),
          ...(elapsedSeconds !== undefined ? { elapsedSeconds } : {}),
          ...(onLabelChange ? { onRename: (label: string) => onLabelChange(s.id, label) } : {}),
        };
        return {
          id: s.id,
          type: "step",
          position: nodePositions?.[s.id] ?? positions.get(s.id) ?? { x: 0, y: 0 },
          selected: s.id === selectedStepId,
          draggable: !readOnly,
          connectable: !readOnly,
          data,
        };
      }),
    [
      steps,
      positions,
      nodePositions,
      selectedStepId,
      actionLabels,
      stepStatuses,
      stepDetails,
      stepTimings,
      readOnly,
      workflowNamesById,
      onLabelChange,
    ],
  );

  const handleNodesChange = (changes: NodeChange<StepFlowNode>[]) => {
    if (!onNodePositionChange) return;
    // Only commit once the drag gesture ends -- committing on every
    // in-flight move would re-render the parent (and thus this component)
    // dozens of times per second for no visual benefit.
    for (const change of changes) {
      if (change.type === "position" && change.dragging === false && change.position) {
        onNodePositionChange(change.id, change.position);
      }
    }
  };

  const edges: Edge[] = useMemo(
    () =>
      steps.flatMap((s) =>
        s.depends_on.map((depId) => ({
          id: `${depId}->${s.id}`,
          source: depId,
          target: s.id,
          animated: stepStatuses?.[s.id] === "running",
          ...(s.trigger_rule === "always" ? { style: { strokeDasharray: "5 4" } } : {}),
        })),
      ),
    [steps, stepStatuses],
  );

  const handleConnect: OnConnect = (connection) => {
    if (readOnly || !onConnectSteps) return;
    if (!connection.source || !connection.target || connection.source === connection.target) return;
    onConnectSteps(connection.source, connection.target);
  };

  return (
    <div className={styles.canvas} style={{ height }} data-testid={testId}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onConnect={handleConnect}
        onNodesChange={handleNodesChange}
        onNodeClick={(_e, node) => onSelectStep?.(node.id)}
        onEdgeClick={(_e, edge) => {
          if (!readOnly) onRemoveDependency?.(edge.source, edge.target);
        }}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
        fitView
        fitViewOptions={{ padding: 0.3 }}
      >
        <Background gap={16} />
        <Controls showInteractive={false} />
        <FitViewOnLayoutChange layoutSignature={layoutSignature} nodes={nodes} />
      </ReactFlow>
    </div>
  );
}

export { NODE_WIDTH, NODE_HEIGHT };
