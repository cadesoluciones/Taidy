import { FabricCatalogManager } from "../components/FabricCatalogManager";

export function GobernanzaDatosPage() {
  return (
    <section>
      <h1>Gobernanza de datos</h1>
      <p>
        Documenta y relaciona los objetos de vuestro workspace de Fabric (notebooks, pipelines, lakehouses) --
        descubiertos en vivo, con descripción y relaciones que se añaden aquí.
      </p>
      <FabricCatalogManager />
    </section>
  );
}
