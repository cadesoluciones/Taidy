const STORAGE_KEY = "taidy.fabricCatalog.recentColors";
const MAX_RECENT = 8;

export function getRecentColors(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

/** Records a just-used color and returns the updated recent list (most
 * recent first, deduped, capped at 8) -- called on every color pick,
 * independent of whether the item ends up being saved. */
export function addRecentColor(color: string): string[] {
  const next = [color, ...getRecentColors().filter((c) => c !== color)].slice(0, MAX_RECENT);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Best-effort only -- a failed write just means it won't be remembered.
  }
  return next;
}
