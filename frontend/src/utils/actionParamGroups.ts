/** Which extra parameter fields an action needs -- shared by SchedulesPage
 * (scheduling one action) and WorkflowsPage (adding it as a flow block), so
 * both stay in sync with what webapp/tasks.py:launch() actually reads out
 * of `params` for each action. */
export const NEEDS_MODE_PARALLEL = new Set(["extract_bc", "sync_bc", "extract_factorial", "sync_factorial"]);
export const NEEDS_START_ON = new Set(["extract_factorial", "sync_factorial"]);
export const NEEDS_SKIP_EXISTING = new Set(["upload_bc", "upload_factorial", "sync_bc", "sync_factorial"]);
