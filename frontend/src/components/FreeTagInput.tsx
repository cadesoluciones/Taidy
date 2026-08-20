import { useState } from "react";

import { X } from "lucide-react";

import styles from "./TagMultiSelect.module.css";

/** Same removable-tag visual as TagMultiSelect, but for fields where the
 * values aren't drawn from a fixed list (owners, free-form tags) -- typing
 * any text and pressing Enter (or the "+" button) adds it. */
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
  const [draft, setDraft] = useState("");

  function commitDraft() {
    const value = draft.trim();
    if (value && !selected.includes(value)) onChange([...selected, value]);
    setDraft("");
  }

  function handleRemove(value: string) {
    onChange(selected.filter((v) => v !== value));
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.tags}>
        {selected.length === 0 && <span className={styles.emptyHint}>{emptyHint}</span>}
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
      </div>
      <input
        id={id}
        type="text"
        className={styles.addSelect}
        placeholder={placeholder}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commitDraft();
          }
        }}
        onBlur={commitDraft}
      />
    </div>
  );
}
