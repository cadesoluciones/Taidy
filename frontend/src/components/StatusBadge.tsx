import { statusMeta } from "./statusMeta";
import styles from "./StatusBadge.module.css";

export function StatusBadge({ status }: { status: string }) {
  const { label, tone } = statusMeta(status);
  return <span className={`${styles.badge} ${styles[tone]}`}>{label || status}</span>;
}
