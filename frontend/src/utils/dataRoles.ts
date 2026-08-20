import type { DataRoleField } from "../api/fabricCatalog";

/** Short label + one-line hint per DAMA-style governance role -- the full
 * explanation (RACI table, worked examples) lives in the help modal on
 * GobernanzaDatosPage, not repeated here. */
export const DATA_ROLE_INFO: Record<DataRoleField, { label: string; hint: string }> = {
  data_owner: { label: "Data Owner", hint: "Decide y responde por el dato." },
  data_steward: { label: "Data Steward", hint: "Define el detalle funcional y supervisa su correcta gestión." },
  data_custodian: { label: "Data Custodian", hint: "Implementa y opera las soluciones técnicas." },
  data_consumer: { label: "Data Consumer", hint: "Utiliza el dato respetando las reglas establecidas." },
};
