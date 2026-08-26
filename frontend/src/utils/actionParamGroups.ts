/** Which extra parameter fields an action needs -- shared by SchedulesPage
 * (scheduling one action) and WorkflowsPage (adding it as a flow block), so
 * both stay in sync with what webapp/tasks.py:launch() actually reads out
 * of `params` for each action. */
export const NEEDS_MODE_PARALLEL = new Set(["extract_bc", "sync_bc", "extract_factorial", "sync_factorial"]);
export const NEEDS_START_ON = new Set(["extract_factorial", "sync_factorial"]);
export const NEEDS_SKIP_EXISTING = new Set(["upload_bc", "upload_factorial", "sync_bc", "sync_factorial"]);

/** Actions whose CLI already accepts a `tables` list (None/empty = every
 * table) -- see webapp/adapter.py's build_*_argv() signatures and
 * webapp/tasks.py:launch(), which forwards `params.tables` straight through
 * untouched for each of these. `upload_bc` is deliberately absent: it just
 * re-uploads whatever CSVs already sit in the output dir, with no table
 * filter of its own. `run_pipeline` and `sync_apply` have no table concept
 * at all (one named pipeline / one named mapping per block). */
export const NEEDS_TABLES = new Set([
  "extract_bc",
  "sync_bc",
  "extract_factorial",
  "upload_factorial",
  "sync_factorial",
  "extract_hubspot",
  "upload_hubspot",
  "sync_hubspot",
]);

/** Which table-catalog system a NEEDS_TABLES action's picker should list. */
export const TABLE_SYSTEM_FOR_ACTION: Record<string, "bc" | "factorial" | "hubspot"> = {
  extract_bc: "bc",
  sync_bc: "bc",
  extract_factorial: "factorial",
  upload_factorial: "factorial",
  sync_factorial: "factorial",
  extract_hubspot: "hubspot",
  upload_hubspot: "hubspot",
  sync_hubspot: "hubspot",
};
