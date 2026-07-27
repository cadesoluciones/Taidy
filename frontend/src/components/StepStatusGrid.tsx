import type { TableStatus } from "../api/types";
import { statusMeta } from "./statusMeta";
import styles from "./StepStatusGrid.module.css";

/** Checklist-card grid for a task's per-table/file status -- one card per
 * item (icon + name + phase + detail), instead of a plain table row. A sync
 * task's upload outcome (if any) renders as a second, smaller icon on the
 * same card instead of a separate card for the same table -- see
 * webapp/adapter.py's merge_sync_statuses(). */
export function StepStatusGrid({ items }: { items: TableStatus[] }) {
  return (
    <div className={styles.grid}>
      {items.map((t) => {
        const { icon: Icon, tone } = statusMeta(t.status);
        const upload = t.upload_status ? statusMeta(t.upload_status) : null;
        return (
          <div className={styles.card} key={t.name}>
            <div className={styles.iconRow}>
              <Icon size={22} className={`${styles.icon} ${styles[tone]}`} aria-hidden="true" />
              {upload && (
                <span className={styles.uploadIconWrap} title={t.upload_detail || upload.label}>
                  <upload.icon
                    size={14}
                    className={`${styles.uploadIcon} ${styles[upload.tone]}`}
                    aria-label={t.upload_detail || upload.label}
                  />
                </span>
              )}
            </div>
            <div className={styles.name}>{t.name}</div>
            {t.phase && <div className={styles.phase}>{t.phase}</div>}
            {t.detail && <div className={styles.detail}>{t.detail}</div>}
            {t.upload_detail && <div className={styles.uploadDetail}>{t.upload_detail}</div>}
          </div>
        );
      })}
    </div>
  );
}
