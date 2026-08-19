/** Spanish label for every action the backend can launch (manually, as a
 * scheduled entry, or as a step inside a workflow) -- SchedulesPage,
 * WorkflowsPage/ReaderHomePage (via WorkflowDiagram) and HistoryPage's
 * action filter all read from this instead of each keeping their own copy.
 */
export const ACTION_LABELS: Record<string, string> = {
  extract_bc: "BC · Extraer",
  upload_bc: "BC · Subir",
  sync_bc: "BC · Sync (extraer + subir)",
  extract_factorial: "Factorial · Extraer",
  upload_factorial: "Factorial · Subir",
  sync_factorial: "Factorial · Sync (extraer + subir)",
  extract_hubspot: "HubSpot · Extraer",
  upload_hubspot: "HubSpot · Subir",
  sync_hubspot: "HubSpot · Sync (extraer + subir)",
  run_pipeline: "Fabric · Ejecutar pipeline",
  sync_apply: "Sincronización · Aplicar",
  run_workflow: "Flujo (varios bloques)",
};
