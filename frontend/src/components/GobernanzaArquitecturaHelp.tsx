import { ArrowDown, ArrowRight, BarChart3, Boxes, Cloud, Database, FileText, Table2 } from "lucide-react";

import styles from "./GobernanzaArquitecturaHelp.module.css";

/** Same icon vocabulary utils/fabricIcons.ts already uses for these same
 * concepts elsewhere in the app (Cloud/Database/Table2/BarChart3), plus
 * Boxes -- confirmed live this is literally the icon Fabric itself shows
 * for a SemanticModel item -- so this diagram reads as "the same things
 * you already see in the catalog", not a generic illustration. */
export function GobernanzaArquitecturaHelp() {
  return (
    <div className={styles.content}>
      <p>
        Fabric organiza los datos en tres capas -- la arquitectura <strong>Medallón</strong> -- y en Taidy cada tabla
        real puede llevar además dos cosas colgando de ella: su <strong>Catálogo</strong> (un diccionario de datos) y,
        si alimenta informes, su <strong>Modelo semántico</strong>.
      </p>

      <div
        className={styles.diagram}
        role="img"
        aria-label="Diagrama: las fuentes (Business Central, HubSpot, Factorial) alimentan Bronze, que alimenta Silver, que alimenta Gold. Cada una de las tres capas tiene su propio Catálogo (diccionario de datos). Gold además tiene un Modelo semántico que conecta con Power BI."
      >
        <div className={`${styles.node} ${styles.nodeSource}`} style={{ gridColumn: 1, gridRow: 1 }}>
          <Cloud size={16} aria-hidden="true" />
          <span>Fuentes</span>
          <small>BC · HubSpot · Factorial</small>
        </div>
        <ArrowRight className={styles.hArrow} size={18} style={{ gridColumn: 2, gridRow: 1 }} aria-hidden="true" />
        <div className={`${styles.node} ${styles.nodeBronze}`} style={{ gridColumn: 3, gridRow: 1 }}>
          <Database size={16} aria-hidden="true" />
          <span>Bronze</span>
          <small>Datos crudos</small>
        </div>
        <ArrowRight className={styles.hArrow} size={18} style={{ gridColumn: 4, gridRow: 1 }} aria-hidden="true" />
        <div className={`${styles.node} ${styles.nodeSilver}`} style={{ gridColumn: 5, gridRow: 1 }}>
          <Table2 size={16} aria-hidden="true" />
          <span>Silver</span>
          <small>Limpios y validados</small>
        </div>
        <ArrowRight className={styles.hArrow} size={18} style={{ gridColumn: 6, gridRow: 1 }} aria-hidden="true" />
        <div className={`${styles.node} ${styles.nodeGold}`} style={{ gridColumn: 7, gridRow: 1 }}>
          <BarChart3 size={16} aria-hidden="true" />
          <span>Gold</span>
          <small>Listos para negocio</small>
        </div>

        <ArrowDown className={styles.vArrow} size={16} style={{ gridColumn: 3, gridRow: 2 }} aria-hidden="true" />
        <div className={`${styles.node} ${styles.nodeCatalog}`} style={{ gridColumn: 3, gridRow: 3 }}>
          <FileText size={14} aria-hidden="true" />
          <span>Catálogo</span>
          <small>tipo · descripción · ejemplo</small>
        </div>

        <ArrowDown className={styles.vArrow} size={16} style={{ gridColumn: 5, gridRow: 2 }} aria-hidden="true" />
        <div className={`${styles.node} ${styles.nodeCatalog}`} style={{ gridColumn: 5, gridRow: 3 }}>
          <FileText size={14} aria-hidden="true" />
          <span>Catálogo</span>
          <small>tipo · descripción · ejemplo</small>
        </div>

        <ArrowDown className={styles.vArrow} size={16} style={{ gridColumn: 7, gridRow: 2 }} aria-hidden="true" />
        <div className={`${styles.node} ${styles.nodeCatalog}`} style={{ gridColumn: 7, gridRow: 3 }}>
          <FileText size={14} aria-hidden="true" />
          <span>Catálogo</span>
          <small>tipo · descripción · ejemplo</small>
        </div>

        <ArrowDown className={styles.vArrow} size={16} style={{ gridColumn: 7, gridRow: 4 }} aria-hidden="true" />
        <div className={`${styles.node} ${styles.nodeModel}`} style={{ gridColumn: 7, gridRow: 5 }}>
          <Boxes size={14} aria-hidden="true" />
          <span>Modelo semántico</span>
          <small>DirectLake · Power BI</small>
        </div>
      </div>
      <p className={styles.diagramNote}>
        Cualquier tabla de cualquier capa puede tener su Catálogo y su Modelo semántico -- lo habitual es que el
        modelo semántico viva sobre Gold, que es lo que suele alimentar un informe.
      </p>

      <h3>Bronze</h3>
      <p>
        Datos tal cual llegan de origen (Business Central, HubSpot, Factorial), sin transformar. Es la copia cruda:
        útil para trazabilidad, no pensada para analizar directamente.
      </p>

      <h3>Silver</h3>
      <p>
        El resultado de limpiar, validar y dar forma a los datos de Bronze: tipos correctos, sin duplicados, con las
        reglas de negocio ya aplicadas.
      </p>

      <h3>Gold</h3>
      <p>Datos ya agregados y listos para consumo -- lo que ve un informe o un análisis final.</p>

      <h3>Catálogo</h3>
      <p>
        El diccionario de datos de una tabla: qué significa cada columna, de qué tipo es y un ejemplo de valor. Se
        edita desde la pestaña <strong>"Catálogo"</strong> de cada tabla Lakehouse. Es lo que el notebook de Fabric{" "}
        <code>catalog_metadata</code> usa para regenerar sus propias tablas <code>catalog.*</code> -- por eso en
        Taidy siempre se edita el diccionario, nunca esa tabla directamente (una ejecución del notebook la
        reescribiría entera).
      </p>

      <h3>Modelo semántico</h3>
      <p>
        Conecta una tabla con Power BI: define las columnas, tipos y relaciones que un informe puede consultar en
        vivo (DirectLake). Se edita desde la pestaña <strong>"Modelo semántico"</strong>.
      </p>
    </div>
  );
}
