import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { Info } from "lucide-react";

import styles from "./InfoTooltip.module.css";

interface InfoTooltipProps {
  text: ReactNode;
  label?: string;
}

/** A small (i) button that reveals a short block of text in a popover on
 * click -- click-to-toggle (not hover), matching this app's existing
 * popover convention (see FabricCatalogManager.tsx's appearance picker),
 * and more usable on touch than a hover-only tooltip. For a rich, longer
 * help guide (several paragraphs, examples), open a <Modal> instead -- see
 * GobernanzaDatosPage.tsx's separate "Ayuda" button for that pattern; this
 * component is only for the one-paragraph page description that used to
 * sit under every page's <h1>. */
export function InfoTooltip({ text, label = "Más información" }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  return (
    <div className={styles.wrap} ref={ref}>
      <button
        type="button"
        className={styles.button}
        aria-label={label}
        aria-expanded={open}
        title={label}
        onClick={() => setOpen((v) => !v)}
      >
        <Info size={14} />
      </button>
      {open && (
        <div className={styles.popover} role="tooltip">
          {text}
        </div>
      )}
    </div>
  );
}
