import { useState } from "react";

import { HelpCircle, Layers } from "lucide-react";

import { FabricCatalogManager } from "../components/FabricCatalogManager";
import { GobernanzaArquitecturaHelp } from "../components/GobernanzaArquitecturaHelp";
import { GobernanzaRolesHelp } from "../components/GobernanzaRolesHelp";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import styles from "./GobernanzaDatosPage.module.css";

export function GobernanzaDatosPage() {
  const [helpOpen, setHelpOpen] = useState(false);
  const [arquitecturaOpen, setArquitecturaOpen] = useState(false);

  return (
    <section>
      <PageHeader
        title="Gobernanza de datos"
        description={
          <>
            Documenta y relaciona los objetos de Fabric, Business Central y HubSpot -- descubiertos en vivo (Fabric)
            o desde su configuración de tablas (BC/HubSpot), con descripción, roles de gobernanza y relaciones que
            se añaden aquí.
          </>
        }
      >
        <button
          type="button"
          className={styles.helpButton}
          onClick={() => setArquitecturaOpen(true)}
          aria-label="Cómo se relacionan Bronze, Silver, Gold, el Catálogo y el Modelo semántico"
          title="Cómo se relacionan Bronze, Silver, Gold, el Catálogo y el Modelo semántico"
        >
          <Layers size={18} />
        </button>
        <button
          type="button"
          className={styles.helpButton}
          onClick={() => setHelpOpen(true)}
          aria-label="Ayuda sobre los roles de gobernanza del dato"
          title="Ayuda sobre los roles de gobernanza del dato"
        >
          <HelpCircle size={18} />
        </button>
      </PageHeader>
      <FabricCatalogManager />

      <Modal
        open={arquitecturaOpen}
        size="large"
        eyebrow="Gobernanza de datos"
        title="Bronze, Silver, Gold, Catálogo y Modelo semántico"
        subtitle="Cómo encaja cada pieza de la arquitectura Medallón en lo que ves aquí."
        onClose={() => setArquitecturaOpen(false)}
      >
        <GobernanzaArquitecturaHelp />
      </Modal>

      <Modal
        open={helpOpen}
        size="large"
        eyebrow="Gobernanza de datos"
        title="Roles de gobernanza del dato"
        subtitle="Qué hace cada rol, con ejemplos y la distribución RACI habitual."
        onClose={() => setHelpOpen(false)}
      >
        <GobernanzaRolesHelp />
      </Modal>
    </section>
  );
}
