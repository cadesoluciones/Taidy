import { Ban, CheckCircle2, Circle, Clock, Loader2, MinusCircle, PauseCircle, StopCircle, XCircle, type LucideIcon } from "lucide-react";

export type StatusTone = "info" | "warning" | "success" | "danger" | "neutral";

interface StatusMeta {
  label: string;
  tone: StatusTone;
  icon: LucideIcon;
}

/**
 * Single source of truth for how every status the backend emits is
 * labeled, colored and iconified. StatusBadge, StepStatusGrid,
 * WorkflowDiagram and OutcomeIcon each used to keep their own copy of this
 * -- they had already drifted (dry_run read as "warning" in one and
 * "neutral" in the other for the exact same meaning).
 */
export const STATUS_META: Record<string, StatusMeta> = {
  running: { label: "En curso", tone: "info", icon: Loader2 },
  stopping: { label: "Deteniendo…", tone: "warning", icon: PauseCircle },
  ok: { label: "Completada", tone: "success", icon: CheckCircle2 },
  error: { label: "Error", tone: "danger", icon: XCircle },
  stopped: { label: "Detenida", tone: "neutral", icon: StopCircle },
  pending: { label: "Pendiente", tone: "neutral", icon: Circle },
  cancelled: { label: "Cancelada", tone: "neutral", icon: Ban },
  skipped: { label: "Omitida", tone: "neutral", icon: MinusCircle },
  dry_run: { label: "Simulada", tone: "warning", icon: MinusCircle },
  unknown: { label: "Desconocido", tone: "neutral", icon: MinusCircle },
  in_progress: { label: "En curso", tone: "info", icon: Clock },
};

const FALLBACK: StatusMeta = { label: "", tone: "neutral", icon: MinusCircle };

/** Never throws on a status the backend might add later -- worst case is a
 * neutral badge showing the raw string, matching the tolerant fallback
 * every one of the four consumers already had individually. */
export function statusMeta(status: string): StatusMeta {
  return STATUS_META[status] ?? { ...FALLBACK, label: status };
}
