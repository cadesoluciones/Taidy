import { useEffect, useState } from "react";

import { fetchBcTables, fetchFactorialTables, fetchHubspotTables } from "../api/meta";
import { TABLE_SYSTEM_FOR_ACTION } from "../utils/actionParamGroups";
import formStyles from "./Form.module.css";
import styles from "./TableScopeField.module.css";
import { TagMultiSelect } from "./TagMultiSelect";

export type TableScopeMode = "all" | "some" | "one";

/** null/undefined/[] on `tables` all mean "todas" to the backend (see
 * webapp/tasks.py:launch()'s `if tables else ...` fallback) -- this derives
 * which of the three UI modes best represents a saved/loaded value, only
 * used to pick the initial mode when a block is selected. Picking "one" for
 * a single saved table (rather than "some" with one tag) is an arbitrary
 * choice between two functionally-identical displays, not a real ambiguity. */
export function tableScopeModeFor(tables: string[] | undefined | null): TableScopeMode {
  if (!tables || tables.length === 0) return "all";
  return tables.length === 1 ? "one" : "some";
}

function fetchTablesFor(action: string): Promise<{ items: string[] }> {
  const system = TABLE_SYSTEM_FOR_ACTION[action];
  if (system === "bc") return fetchBcTables();
  if (system === "factorial") return fetchFactorialTables();
  if (system === "hubspot") return fetchHubspotTables();
  return Promise.resolve({ items: [] });
}

interface TableScopeFieldProps {
  idPrefix: string;
  action: string;
  mode: TableScopeMode;
  onModeChange: (mode: TableScopeMode) => void;
  tables: string[];
  onTablesChange: (tables: string[]) => void;
}

/** The "Todas / Algunas / Una concreta" tables scope a flow block (or a
 * scheduled task, in the future) restricts an extract/upload/sync action
 * to -- see NEEDS_TABLES. Mirrors BcExtractPage.tsx's "empty selection =
 * all tables" convention, just with an explicit 3-way toggle on top for
 * discoverability instead of relying on an unlabeled empty picker. */
export function TableScopeField({ idPrefix, action, mode, onModeChange, tables, onTablesChange }: TableScopeFieldProps) {
  const [options, setOptions] = useState<string[]>([]);

  useEffect(() => {
    fetchTablesFor(action)
      .then((res) => setOptions(res.items))
      .catch(() => setOptions([]));
  }, [action]);

  return (
    <div className={formStyles.field}>
      <label>Tablas</label>
      <div className={styles.modeRow}>
        <button
          type="button"
          className={mode === "all" ? styles.modeActive : styles.mode}
          onClick={() => onModeChange("all")}
        >
          Todas
        </button>
        <button
          type="button"
          className={mode === "some" ? styles.modeActive : styles.mode}
          onClick={() => onModeChange("some")}
        >
          Algunas
        </button>
        <button
          type="button"
          className={mode === "one" ? styles.modeActive : styles.mode}
          onClick={() => onModeChange("one")}
        >
          Una concreta
        </button>
      </div>
      {mode === "some" && (
        <TagMultiSelect
          id={`${idPrefix}_tables`}
          options={options}
          selected={tables}
          onChange={onTablesChange}
          emptyHint="Elige al menos una tabla -- vacío se trata como todas"
        />
      )}
      {mode === "one" && (
        <select
          id={`${idPrefix}_table`}
          value={tables[0] ?? ""}
          onChange={(e) => onTablesChange(e.target.value ? [e.target.value] : [])}
        >
          <option value="">Selecciona una tabla…</option>
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
