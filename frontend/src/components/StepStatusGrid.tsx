import { CheckCircle2, Clock, MinusCircle, XCircle, type LucideIcon } from "lucide-react";

import type { TableStatus, TableStatusValue } from "../api/types";
import styles from "./StepStatusGrid.module.css";

const STATUS_ICON: Record<TableStatusValue, { icon: LucideIcon; tone: "success" | "danger" | "info" | "neutral" }> = {
  ok: { icon: CheckCircle2, tone: "success" },
  in_progress: { icon: Clock, tone: "info" },
  error: { icon: XCircle, tone: "danger" },
  skipped: { icon: MinusCircle, tone: "neutral" },
  dry_run: { icon: MinusCircle, tone: "neutral" },
  unknown: { icon: MinusCircle, tone: "neutral" },
};

/** Checklist-card grid for a task's per-table/file status -- one card per
 * item (icon + name + phase + detail), instead of a plain table row. */
export function StepStatusGrid({ items }: { items: TableStatus[] }) {
  return (
    <div className={styles.grid}>
      {items.map((t) => {
        const { icon: Icon, tone } = STATUS_ICON[t.status] ?? STATUS_ICON.unknown;
        return (
          <div className={styles.card} key={`${t.phase}-${t.name}`}>
            <Icon size={22} className={`${styles.icon} ${styles[tone]}`} aria-hidden="true" />
            <div className={styles.name}>{t.name}</div>
            {t.phase && <div className={styles.phase}>{t.phase}</div>}
            {t.detail && <div className={styles.detail}>{t.detail}</div>}
          </div>
        );
      })}
    </div>
  );
}
