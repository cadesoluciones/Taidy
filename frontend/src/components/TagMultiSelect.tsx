import { X } from "lucide-react";

import styles from "./TagMultiSelect.module.css";

/** Replaces a native `<select multiple>` for picking tables -- that control
 * requires ctrl/cmd-click to deselect an option, which isn't discoverable,
 * so once something was picked it looked impossible to clear. Selected
 * values render as removable tags instead; a plain single-value `<select>`
 * (still `id`-addressable like the old control, so existing lookups by id
 * keep working) is used just to add the next one. */
export function TagMultiSelect({
  id,
  options,
  selected,
  onChange,
  placeholder = "+ Añadir tabla…",
  emptyHint = "Vacío = todas",
}: {
  id: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  emptyHint?: string;
}) {
  const available = options.filter((o) => !selected.includes(o));

  function handleAdd(e: React.ChangeEvent<HTMLSelectElement>) {
    const value = e.target.value;
    if (!value) return;
    onChange([...selected, value]);
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
      <select id={id} className={styles.addSelect} value="" onChange={handleAdd} disabled={available.length === 0}>
        <option value="" disabled>
          {available.length === 0 ? "No hay más tablas disponibles" : placeholder}
        </option>
        {available.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
