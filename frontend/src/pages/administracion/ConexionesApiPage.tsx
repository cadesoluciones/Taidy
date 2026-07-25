import { BcTableManager } from "../../components/BcTableManager";
import { FactorialTableManager } from "../../components/FactorialTableManager";

export function ConexionesApiPage() {
  return (
    <section>
      <h1>Conexiones API</h1>
      <p>
        Añade, edita o elimina las tablas disponibles para extracción de Business Central y Factorial HR. Se escribe
        directamente en <code>tables.yaml</code> / <code>factorial_tables.yaml</code> — los mismos ficheros que ya
        usan las extracciones reales, así que un cambio aquí está disponible al momento en los formularios de
        Ejecutar.
      </p>

      <h2>Business Central</h2>
      <BcTableManager />

      <h2>Factorial HR</h2>
      <FactorialTableManager />
    </section>
  );
}
