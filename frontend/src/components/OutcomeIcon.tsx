import { CheckCircle2, StopCircle, XCircle } from "lucide-react";

/** Shared "how did this run end" icon -- used by HomePage's recent-activity
 * list and HistoryPage's entries so the same run-outcome reads identically
 * everywhere instead of each page picking its own icon/color. */
export function OutcomeIcon({ ok, status }: { ok: boolean; status?: string }) {
  if (ok) {
    return <CheckCircle2 size={16} color="var(--color-success)" aria-label="Completada correctamente" />;
  }
  if (status === "stopped") {
    return <StopCircle size={16} color="var(--color-text-muted)" aria-label="Detenida" />;
  }
  return <XCircle size={16} color="var(--color-danger)" aria-label="Error" />;
}
