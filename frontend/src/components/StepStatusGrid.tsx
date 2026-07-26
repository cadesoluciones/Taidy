import type { TableStatus } from "../api/types";
import { statusMeta } from "./statusMeta";
import styles from "./StepStatusGrid.module.css";

/** Checklist-card grid for a task's per-table/file status -- one card per
 * item (icon + name + phase + detail), instead of a plain table row. */
export function StepStatusGrid({ items }: { items: TableStatus[] }) {
  return (
    <div className={styles.grid}>
      {items.map((t) => {
        const { icon: Icon, tone } = statusMeta(t.status);
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
