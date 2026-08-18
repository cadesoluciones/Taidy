/** Appends `name` to a comma-separated fields string, deduplicating --
 * shared by every *TableManager that lets a picked property/field
 * (AvailablePropertiesPicker) be added to its "propiedades/campos a
 * conservar" text input with one click. */
export function appendField(raw: string, name: string): string {
  const existing = raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (existing.includes(name)) return raw;
  return existing.length > 0 ? `${raw.trimEnd()}, ${name}` : name;
}
