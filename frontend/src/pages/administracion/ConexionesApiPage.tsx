import { BcTableManager } from "../../components/BcTableManager";
import { FactorialTableManager } from "../../components/FactorialTableManager";
import { HubspotTableManager } from "../../components/HubspotTableManager";
import { PageHeader } from "../../components/PageHeader";

export function ConexionesApiPage() {
  return (
    <section>
      <PageHeader
        title="Conexiones API"
        description={
          <>
            Añade, edita o elimina las tablas disponibles para extracción de Business Central, Factorial HR y
            HubSpot CRM. Se escribe directamente en <code>tables.yaml</code> / <code>factorial_tables.yaml</code> /{" "}
            <code>hubspot_tables.yaml</code> — los mismos ficheros que ya usan las extracciones reales, así que un
            cambio aquí está disponible al momento en los formularios de Ejecutar.
          </>
        }
      />

      <h2>Business Central</h2>
      <BcTableManager />

      <h2>Factorial HR</h2>
      <FactorialTableManager />

      <h2>HubSpot CRM</h2>
      <HubspotTableManager />
    </section>
  );
}
