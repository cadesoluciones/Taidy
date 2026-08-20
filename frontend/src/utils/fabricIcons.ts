import {
  BarChart3,
  Boxes,
  Cloud,
  Database,
  FileText,
  Folder,
  GitBranch,
  Link2,
  Pencil,
  Server,
  Table2,
  Workflow,
  type LucideIcon,
} from "lucide-react";

/** Fixed, small icon vocabulary for governance blocks -- kept in sync with
 * webapp/fabric_catalog.py's ICON_KEYS (a stored key the backend doesn't
 * recognize is rejected, so this list and that set must match). */
export const FABRIC_ICON_OPTIONS: { key: string; label: string; Icon: LucideIcon }[] = [
  { key: "database", label: "Base de datos", Icon: Database },
  { key: "table", label: "Tabla", Icon: Table2 },
  { key: "file", label: "Archivo", Icon: FileText },
  { key: "pipeline", label: "Pipeline", Icon: Workflow },
  { key: "warehouse", label: "Warehouse", Icon: Server },
  { key: "cloud", label: "Nube", Icon: Cloud },
  { key: "external", label: "Externo", Icon: Link2 },
  { key: "manual", label: "Manual", Icon: Pencil },
  { key: "folder", label: "Carpeta", Icon: Folder },
  { key: "chart", label: "Gráfico", Icon: BarChart3 },
  { key: "boxes", label: "Colección", Icon: Boxes },
  { key: "git", label: "Origen/control", Icon: GitBranch },
];

const ICON_BY_KEY = new Map(FABRIC_ICON_OPTIONS.map((o) => [o.key, o.Icon]));

export function fabricIconFor(key: string): LucideIcon | null {
  return ICON_BY_KEY.get(key) ?? null;
}
