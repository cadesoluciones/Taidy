import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

import styles from "./Modal.module.css";

interface ModalProps {
  open: boolean;
  eyebrow?: string;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  /** "large" gives the dialog much more width/height -- for content that
   * needs real room (a canvas editor), not the ~760px management panels
   * this component was originally sized for. */
  size?: "default" | "large";
}

/** Generic large dialog (native <dialog>, same focus-trap/Escape behavior as
 * ConfirmDialog) for management panels -- currently the "Gestión de
 * usuarios" directory, opened from the header icon. */
export function Modal({ open, eyebrow, title, subtitle, onClose, children, size = "default" }: ModalProps) {
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
    <dialog
      ref={ref}
      className={size === "large" ? `${styles.dialog} ${styles.dialogLarge}` : styles.dialog}
      onCancel={onClose}
      onClose={onClose}
    >
      <div className={styles.header}>
        <div>
          {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
          <h2 className={styles.title}>{title}</h2>
          {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        </div>
        <button type="button" className={styles.close} aria-label="Cerrar" onClick={onClose}>
          <X size={18} />
        </button>
      </div>
      <div className={styles.body}>{children}</div>
    </dialog>
  );
}
