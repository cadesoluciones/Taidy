import type { ReactNode } from "react";

import styles from "./Timeline.module.css";

export interface TimelineItem {
  key: string;
  title: ReactNode;
  description?: ReactNode;
  timestamp?: string;
  icon?: ReactNode;
  tone?: "success" | "danger" | "neutral" | "info";
  /** Visually marks this row as related to whatever the caller currently
   * has selected/focused (e.g. HistoryPage highlighting every entry that
   * shares a workflow_run_id) -- purely cosmetic, doesn't affect order. */
  highlighted?: boolean;
}

export function Timeline({ items, emptyLabel }: { items: TimelineItem[]; emptyLabel: string }) {
  if (items.length === 0) {
    return <p>{emptyLabel}</p>;
  }

  return (
    <ol className={styles.timeline}>
      {items.map((item) => (
        <li key={item.key} className={item.highlighted ? `${styles.item} ${styles.itemHighlighted}` : styles.item}>
          <span className={`${styles.dot} ${item.tone ? styles[item.tone] : ""}`} aria-hidden="true">
            {item.icon}
          </span>
          <div className={styles.body}>
            <div className={styles.head}>
              <span className={styles.title}>{item.title}</span>
              {item.timestamp && <span className={styles.timestamp}>{item.timestamp}</span>}
            </div>
            {item.description && <div className={styles.description}>{item.description}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}
