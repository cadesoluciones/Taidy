import { useEffect, useRef, useState } from "react";

import { Plus, X } from "lucide-react";

import styles from "./FreeTagInput.module.css";

/** Compact tag input for fields where the values aren't drawn from a fixed
 * list (owners, free-form tags): tags and a small "+" button share one
 * line, and "+" opens a tiny popup to type the next value instead of
 * always reserving a full input row below the tags. */
export function FreeTagInput({
  id,
  selected,
  onChange,
  placeholder = "Escribe y pulsa Enter…",
  emptyHint = "Sin valores",
}: {
  id: string;
  selected: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  emptyHint?: string;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
        setDraft("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  function commitDraft() {
    const value = draft.trim();
    if (value && !selected.includes(value)) onChange([...selected, value]);
    setDraft("");
    inputRef.current?.focus();
  }

  function handleRemove(value: string) {
    onChange(selected.filter((v) => v !== value));
  }

  return (
    <div className={styles.wrapper} ref={wrapperRef}>
      <div className={styles.tagsRow}>
        {selected.length === 0 && !open && <span className={styles.emptyHint}>{emptyHint}</span>}
        {selected.map((value) => (
          <span key={value} className={styles.tag}>
            {value}
            <button
              type="button"
              className={styles.tagRemove}
              aria-label={`Quitar ${value}`}
              onClick={() => handleRemove(value)}
            >
              <X size={11} />
            </button>
          </span>
        ))}
        <button type="button" className={styles.addButton} aria-label={placeholder} onClick={() => setOpen(true)}>
          <Plus size={12} />
        </button>
      </div>
      {open && (
        <div className={styles.addPopup}>
          <input
            ref={inputRef}
            id={id}
            type="text"
            placeholder={placeholder}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commitDraft();
              } else if (e.key === "Escape") {
                setOpen(false);
                setDraft("");
              }
            }}
          />
          <button type="button" className={styles.addPopupSubmit} onClick={commitDraft}>
            Añadir
          </button>
        </div>
      )}
    </div>
  );
}
