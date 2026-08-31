import { PageHeader } from "../../components/PageHeader";
import { SyncMappingManager } from "../../components/SyncMappingManager";

export function MapeosPage() {
  return (
    <section>
      <PageHeader
        title="Mapeos de sincronización"
        description={
          <>
            Define qué campo de una tabla corresponde a qué campo de otra, y cuál es la clave y el campo de fecha
            que identifican al mismo registro en ambos lados (ej. el email y la fecha de modificación de un
            contacto). Esto solo guarda el mapeo en <code>sync_mappings.yaml</code> — no sincroniza nada por sí
            mismo, para eso está Sincronización → Comparar.
          </>
        }
      />
      <SyncMappingManager />
    </section>
  );
}
