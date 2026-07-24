import { useEffect, useRef } from "react";

import styles from "./ConfirmDialog.module.css";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * One dialog component reused for all destructive/high-impact actions
 * (delete user, delete workflow, delete schedule, stop task, stop workflow,
 * change role) -- mirrors webapp/app.py's own "one pattern, six call sites"
 * design (Fase 1 ND-01). Uses the native <dialog> element for built-in focus
 * trapping and Escape-to-close.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirmar",
  danger = true,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog ref={ref} className={styles.dialog} onCancel={onCancel} onClose={onCancel}>
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.description}>{description}</p>
      <div className={styles.actions}>
        <button type="button" className={styles.cancel} onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
        <button
          type="button"
          className={danger ? styles.confirmDanger : styles.confirm}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? "Aplicando…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
