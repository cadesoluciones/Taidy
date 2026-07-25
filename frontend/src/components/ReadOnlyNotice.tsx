import { Eye } from "lucide-react";

import styles from "./ReadOnlyNotice.module.css";

export function ReadOnlyNotice({ action = "ejecutar esta acción" }: { action?: string }) {
  return (
    <div className={styles.notice}>
      <Eye size={16} aria-hidden="true" />
      <span>
        <strong>Modo consulta.</strong> Tu rol (Lector) permite ver esta página pero no {action}.
      </span>
    </div>
  );
}
