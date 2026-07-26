import { statusMeta } from "./statusMeta";

/** Shared "how did this run end" icon -- used by HomePage's recent-activity
 * list and HistoryPage's entries so the same run-outcome reads identically
 * everywhere instead of each page picking its own icon/color. */
export function OutcomeIcon({ ok, status }: { ok: boolean; status?: string }) {
  if (ok) {
    const { icon: Icon } = statusMeta("ok");
    return <Icon size={16} color="var(--color-success)" aria-label="Completada correctamente" />;
  }
  if (status === "stopped") {
    const { icon: Icon } = statusMeta("stopped");
    return <Icon size={16} color="var(--color-text-muted)" aria-label="Detenida" />;
  }
  const { icon: Icon } = statusMeta("error");
  return <Icon size={16} color="var(--color-danger)" aria-label="Error" />;
}
