import { useState } from "react";

import { ApiError } from "../api/client";
import type { AvailableProperty } from "../api/meta";
import formStyles from "./Form.module.css";
import styles from "./AvailablePropertiesPicker.module.css";

interface AvailablePropertiesPickerProps {
  buttonLabel?: string;
  disabled?: boolean;
  disabledHint?: string;
  /** Only meaningful for systems with a "hidden/calculated" concept (HubSpot) --
   * omit entirely for systems that don't (Factorial's sampled fields have no
   * such distinction). */
  showHiddenToggle?: boolean;
  fetchProperties: (includeHidden: boolean) => Promise<{ items: AvailableProperty[] }>;
  /** Gets the whole picked entry, not just its `name` -- most callers only
   * need `.name` (unchanged from before), but one (BC's table URL picker)
   * needs `.label` too, since its "name" is a long URL unsuited to being
   * the bold, primary text every row shows -- there it's the short,
   * scannable identifier instead, with the full URL carried in `.label`. */
  onPick: (property: AvailableProperty) => void;
}

/** Admin-only helper: a button that opens a live, searchable, click-to-add
 * list of every property/field a system exposes for whatever object
 * type/path/endpoint is currently typed in the surrounding form -- so
 * registering a new table doesn't require already knowing that system's
 * internal field names by heart. Reused identically by HubspotTableManager
 * and FactorialTableManager (and any future *TableManager with the same
 * "curate a fields list" shape); only `fetchProperties` differs per system. */
export function AvailablePropertiesPicker({
  buttonLabel = "Ver propiedades disponibles",
  disabled = false,
  disabledHint,
  showHiddenToggle = false,
  fetchProperties,
  onPick,
}: AvailablePropertiesPickerProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [properties, setProperties] = useState<AvailableProperty[] | null>(null);
  const [includeHidden, setIncludeHidden] = useState(false);
  const [query, setQuery] = useState("");

  async function load(nextIncludeHidden: boolean) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchProperties(nextIncludeHidden);
      setProperties(res.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudieron cargar las propiedades disponibles.");
      setProperties(null);
    } finally {
      setLoading(false);
    }
  }

  async function toggleOpen() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setQuery("");
    await load(includeHidden);
  }

  const trimmedQuery = query.trim().toLowerCase();
  const visible = (properties ?? []).filter(
    (p) => !trimmedQuery || p.name.toLowerCase().includes(trimmedQuery) || p.label.toLowerCase().includes(trimmedQuery)
  );

  return (
    <div className={styles.wrap}>
      <button type="button" className={styles.toggleBtn} disabled={disabled} onClick={() => void toggleOpen()}>
        {buttonLabel}
      </button>
      {disabled && disabledHint && <p className={formStyles.hint}>{disabledHint}</p>}

      {open && !disabled && (
        <div className={styles.panel}>
          {loading && <p className={formStyles.hint}>Cargando…</p>}
          {error && <div className={formStyles.errorBanner}>{error}</div>}

          {!loading && !error && (
            <>
              <div className={styles.panelHeader}>
                <input
                  type="text"
                  className={styles.search}
                  placeholder="Buscar…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                {showHiddenToggle && (
                  <label className={styles.hiddenToggle}>
                    <input
                      type="checkbox"
                      checked={includeHidden}
                      onChange={(e) => {
                        const next = e.target.checked;
                        setIncludeHidden(next);
                        void load(next);
                      }}
                    />
                    Mostrar todas (incl. ocultas/calculadas)
                  </label>
                )}
              </div>
              <div className={styles.list}>
                {visible.length === 0 && <p className={styles.emptyHint}>Sin resultados.</p>}
                {visible.map((p) => (
                  <button type="button" key={p.name} className={styles.propertyRow} onClick={() => onPick(p)}>
                    <span className={styles.propertyName}>{p.name}</span>
                    {p.label && p.label !== p.name && <span className={styles.propertyLabel}>{p.label}</span>}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
