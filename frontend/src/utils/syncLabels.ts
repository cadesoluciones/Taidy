import type { SyncApplyDirection } from "../api/tasks";

export const SYSTEM_LABELS: Record<string, string> = {
  business_central: "Business Central",
  factorial: "Factorial HR",
  hubspot: "HubSpot CRM",
};

/** "to_target"/"to_source" mean nothing on their own -- name the actual
 * systems instead, so it's always clear whether a given run means
 * BC→HubSpot or HubSpot→BC (which depends on which system this particular
 * mapping declares as "source" vs "target"). Shared by CompararPage and
 * SyncApplyFields (schedules/workflow steps) so a scheduled/flow-driven
 * sync reads exactly as clearly as a manual one. */
export function directionLabel(direction: SyncApplyDirection, sourceLabel: string, targetLabel: string): string {
  if (direction === "to_target") return `${sourceLabel} → ${targetLabel}`;
  if (direction === "to_source") return `${targetLabel} → ${sourceLabel}`;
  return `Ambas direcciones (${sourceLabel} ↔ ${targetLabel})`;
}
