import { useEffect, useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type OnConnect,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import styles from "./WorkflowDiagram.module.css";

/** Structural subset shared by StepDefinition (draft/saved steps) and
 * StepRun (live run steps) -- the diagram only ever needs these fields,
 * so it accepts either without the caller reshaping data. */
export interface DiagramStep {
  id: string;
  label: string;
  action: string;
  depends_on: string[];
  trigger_rule: string;
}

type StepNodeData = Record<string, unknown> & {
  label: string;
  actionLabel: string;
  status?: string;
  alwaysRun?: boolean;
};

type StepFlowNode = Node<StepNodeData, "step">;

const STATUS_LABELS: Record<string, string> = {
  pending: "pendiente",
  running: "en curso",
  ok: "correcto",
  error: "error",
  cancelled: "cancelado",
  stopped: "detenido",
};

function StepNode({ data, selected }: NodeProps<StepFlowNode>) {
  const status = data.status;
  return (
    <div className={styles.node} data-selected={selected || undefined} data-status={status ?? "none"}>
      <Handle type="target" position={Position.Left} className={styles.handle} />
      <div className={styles.nodeLabel}>{data.label}</div>
      <div className={styles.nodeAction}>{data.actionLabel}</div>
      {status && <div className={styles.nodeStatus}>{STATUS_LABELS[status] ?? status}</div>}
      {data.alwaysRun && <div className={styles.nodeHint}>se lanza aunque falle una dependencia</div>}
      <Handle type="source" position={Position.Right} className={styles.handle} />
    </div>
  );
}

const nodeTypes = { step: StepNode };

/** React Flow's `fitView` prop only re-centers the viewport on the initial
 * mount -- adding a block, or connecting one (which can shift a node into a
 * new dependency layer, see layoutSteps()), repositions nodes without ever
 * re-fitting, so newly-placed nodes/edges can land outside the viewport that
 * was fit around the ORIGINAL, smaller layout. Re-fit whenever the layout
 * signature (which id sits at which position) actually changes. */
function FitViewOnLayoutChange({ layoutSignature }: { layoutSignature: string }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    // No animation duration -- an animated re-fit leaves a window where a
    // node's on-screen position doesn't match its final, settled position
    // yet, which is exactly the kind of window a drag-to-connect gesture
    // (grabbing a handle's coordinates once, up front) can land in.
    fitView({ padding: 0.3 });
    // fitView identity is stable per ReactFlow instance; only the signature should retrigger this.
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
  selectedStepId?: string | null;
  onSelectStep?: (id: string) => void;
  onConnectSteps?: (sourceId: string, targetId: string) => void;
  onRemoveDependency?: (sourceId: string, targetId: string) => void;
  readOnly?: boolean;
  height?: number;
  testId?: string;
}

export function WorkflowDiagram({
  steps,
  actionLabels,
  stepStatuses,
  selectedStepId,
  onSelectStep,
  onConnectSteps,
  onRemoveDependency,
  readOnly = false,
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
        const data: StepNodeData = {
          label: s.label,
          actionLabel: actionLabels[s.action] ?? s.action,
          alwaysRun: s.depends_on.length > 0 && s.trigger_rule === "always",
          ...(status !== undefined ? { status } : {}),
        };
        return {
          id: s.id,
          type: "step",
          position: positions.get(s.id) ?? { x: 0, y: 0 },
          selected: s.id === selectedStepId,
          draggable: !readOnly,
          connectable: !readOnly,
          data,
        };
      }),
    [steps, positions, selectedStepId, actionLabels, stepStatuses, readOnly],
  );

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
        <FitViewOnLayoutChange layoutSignature={layoutSignature} />
      </ReactFlow>
    </div>
  );
}

export { NODE_WIDTH, NODE_HEIGHT };
