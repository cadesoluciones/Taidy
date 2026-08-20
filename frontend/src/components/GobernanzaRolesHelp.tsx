import styles from "./GobernanzaRolesHelp.module.css";

const SITUATIONS: { situation: string; owner: string; steward: string; custodian: string; consumer: string }[] = [
  {
    situation: 'Definición de "cliente activo"',
    owner: "Aprueba la definición oficial",
    steward: "Propone y documenta la definición",
    custodian: "Configura la lógica en sistemas e informes",
    consumer: "Usa la definición en sus análisis",
  },
  {
    situation: "Calidad del dato",
    owner: "Fija objetivos y prioridades",
    steward: "Monitoriza la calidad y coordina incidencias",
    custodian: "Implementa validaciones y correcciones técnicas",
    consumer: "Informa de errores detectados",
  },
  {
    situation: "Acceso a datos",
    owner: "Autoriza el acceso",
    steward: "Comprueba que la solicitud cumple las reglas",
    custodian: "Configura permisos y perfiles",
    consumer: "Accede únicamente para el uso autorizado",
  },
  {
    situation: "Datos duplicados",
    owner: "Aprueba la política de deduplicación",
    steward: "Identifica casos y define reglas de resolución",
    custodian: "Implementa controles y procesos automáticos",
    consumer: "Evita crear registros duplicados",
  },
  {
    situation: "Datos sensibles",
    owner: "Decide qué usos están permitidos",
    steward: "Clasifica y documenta los datos",
    custodian: "Aplica cifrado, enmascaramiento y controles",
    consumer: "Protege los datos y no los comparte indebidamente",
  },
  {
    situation: "Retención y borrado",
    owner: "Aprueba los plazos",
    steward: "Documenta y supervisa su cumplimiento",
    custodian: "Configura archivado y borrado automático",
    consumer: "No conserva copias fuera de los plazos",
  },
  {
    situation: "Cambio de un campo",
    owner: "Aprueba el cambio de negocio",
    steward: "Define requisitos y analiza impactos",
    custodian: "Modifica bases de datos e integraciones",
    consumer: "Adapta informes y procesos",
  },
  {
    situation: "Incidencia de datos",
    owner: "Prioriza y acepta el riesgo",
    steward: "Registra, analiza y coordina la solución",
    custodian: "Corrige el problema técnico",
    consumer: "Comunica el problema y valida el resultado",
  },
];

const RACI_ROWS: { activity: string; owner: string; steward: string; custodian: string; consumer: string }[] = [
  { activity: "Aprobar definiciones", owner: "A", steward: "R", custodian: "C", consumer: "C" },
  { activity: "Mantener el glosario", owner: "C", steward: "R", custodian: "C", consumer: "I" },
  { activity: "Establecer objetivos de calidad", owner: "A", steward: "R/C", custodian: "C", consumer: "I" },
  { activity: "Monitorizar la calidad", owner: "I", steward: "R", custodian: "C", consumer: "C" },
  { activity: "Autorizar accesos", owner: "A", steward: "R/C", custodian: "I", consumer: "I" },
  { activity: "Configurar permisos", owner: "I", steward: "C", custodian: "R", consumer: "I" },
  { activity: "Implantar controles técnicos", owner: "I", steward: "C", custodian: "R", consumer: "I" },
  { activity: "Comunicar errores de datos", owner: "I", steward: "A/R", custodian: "C", consumer: "R" },
  { activity: "Resolver conflictos de negocio", owner: "A", steward: "R", custodian: "C", consumer: "C" },
  { activity: "Usar correctamente los datos", owner: "I", steward: "C", custodian: "C", consumer: "R/A" },
];

interface ExampleRole {
  title: string;
  bullets: string[];
}

interface Example {
  title: string;
  intro: string;
  roles: ExampleRole[];
}

const EXAMPLES: Example[] = [
  {
    title: "Ejemplo 1: datos de clientes",
    intro: "Supongamos que se detectan clientes duplicados en el CRM.",
    roles: [
      {
        title: "Data Owner — Director comercial",
        bullets: [
          "Decide cuál será la política corporativa de identificación de clientes.",
          "Aprueba el nivel máximo de duplicados aceptable.",
          "Prioriza recursos para resolver el problema.",
          "Responde por el impacto comercial.",
        ],
      },
      {
        title: "Data Steward — Responsable funcional del CRM",
        bullets: [
          "Analiza las causas de los duplicados.",
          "Define las reglas para identificar y fusionar registros.",
          "Documenta las reglas en el catálogo o glosario.",
          "Supervisa periódicamente el porcentaje de duplicados.",
        ],
      },
      {
        title: "Data Custodian — Administrador del CRM o equipo de TI",
        bullets: [
          "Configura campos obligatorios y validaciones.",
          "Implementa el proceso automático de deduplicación.",
          "Gestiona permisos, copias de seguridad y trazabilidad.",
          "Corrige errores técnicos del sistema.",
        ],
      },
      {
        title: "Data Consumer — Comercial o analista de ventas",
        bullets: [
          "Consulta y actualiza los datos de clientes.",
          "Busca al cliente antes de crear uno nuevo.",
          "Utiliza únicamente los datos necesarios.",
          "Comunica registros incorrectos o duplicados.",
        ],
      },
    ],
  },
  {
    title: "Ejemplo 2: datos de empleados",
    intro: "Se detecta que muchos empleados no tienen informado correctamente su departamento.",
    roles: [
      {
        title: "Data Owner — Director de Recursos Humanos",
        bullets: [
          "Decide que el departamento es un dato obligatorio.",
          "Establece un objetivo del 99 % de completitud.",
          "Aprueba la modificación del proceso de altas.",
        ],
      },
      {
        title: "Data Steward — Responsable funcional de RR. HH.",
        bullets: [
          "Identifica los registros incompletos.",
          'Define los valores válidos para el campo "departamento".',
          "Coordina la corrección con los responsables de RR. HH.",
          "Monitoriza el cumplimiento del 99 %.",
        ],
      },
      {
        title: "Data Custodian — Administrador del sistema de RR. HH.",
        bullets: [
          "Configura el campo como obligatorio.",
          "Implementa la lista de departamentos válidos.",
          "Configura permisos para proteger los datos personales.",
          "Genera controles automáticos de registros incompletos.",
        ],
      },
      {
        title: "Data Consumer — Responsable de departamento o analista de RR. HH.",
        bullets: [
          "Utiliza los datos para planificación e informes.",
          "No modifica información sin autorización.",
          "Comunica errores al Data Steward.",
          "Respeta las restricciones de confidencialidad.",
        ],
      },
    ],
  },
  {
    title: "Ejemplo 3: acceso a información financiera",
    intro: "Un analista solicita acceso a información detallada sobre costes.",
    roles: [
      {
        title: "Data Owner — Director financiero",
        bullets: [
          "Decide si el acceso está justificado.",
          "Aprueba o rechaza la solicitud.",
          "Determina el nivel de detalle permitido.",
        ],
      },
      {
        title: "Data Steward — Controller o responsable del dato financiero",
        bullets: [
          "Verifica la finalidad de la solicitud.",
          "Comprueba qué campos necesita realmente el analista.",
          "Documenta el acceso y sus condiciones.",
          "Revisa periódicamente si sigue siendo necesario.",
        ],
      },
      {
        title: "Data Custodian — Administrador del ERP o base de datos",
        bullets: [
          "Crea el perfil de acceso.",
          "Configura permisos de solo lectura.",
          "Aplica enmascaramiento cuando corresponda.",
          "Registra accesos y mantiene logs de auditoría.",
        ],
      },
      {
        title: "Data Consumer — Analista financiero",
        bullets: [
          "Utiliza la información para la finalidad autorizada.",
          "No descarga ni comparte datos sin permiso.",
          "Respeta las medidas de seguridad.",
          "Solicita la corrección de datos incorrectos.",
        ],
      },
    ],
  },
];

export function GobernanzaRolesHelp() {
  return (
    <div className={styles.content}>
      <p>La relación entre los cuatro roles puede resumirse así:</p>
      <ul className={styles.roleList}>
        <li>
          <strong>Data Owner:</strong> decide y responde por el dato.
        </li>
        <li>
          <strong>Data Steward:</strong> define el detalle funcional y supervisa su correcta gestión.
        </li>
        <li>
          <strong>Data Custodian:</strong> implementa y opera las soluciones técnicas.
        </li>
        <li>
          <strong>Data Consumer:</strong> utiliza el dato respetando las reglas establecidas.
        </li>
      </ul>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Situación</th>
              <th>Data Owner</th>
              <th>Data Steward</th>
              <th>Data Custodian</th>
              <th>Data Consumer</th>
            </tr>
          </thead>
          <tbody>
            {SITUATIONS.map((row) => (
              <tr key={row.situation}>
                <td>{row.situation}</td>
                <td>{row.owner}</td>
                <td>{row.steward}</td>
                <td>{row.custodian}</td>
                <td>{row.consumer}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {EXAMPLES.map((example) => (
        <div key={example.title} className={styles.example}>
          <h4>{example.title}</h4>
          <p className={styles.exampleIntro}>{example.intro}</p>
          {example.roles.map((role) => (
            <div key={role.title} className={styles.roleBlock}>
              <strong>{role.title}</strong>
              <ul>
                {role.bullets.map((bullet) => (
                  <li key={bullet}>{bullet}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ))}

      <h3>Distribución RACI habitual</h3>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Actividad</th>
              <th>Data Owner</th>
              <th>Data Steward</th>
              <th>Data Custodian</th>
              <th>Data Consumer</th>
            </tr>
          </thead>
          <tbody>
            {RACI_ROWS.map((row) => (
              <tr key={row.activity}>
                <td>{row.activity}</td>
                <td>{row.owner}</td>
                <td>{row.steward}</td>
                <td>{row.custodian}</td>
                <td>{row.consumer}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.legend}>
        <div>
          <strong>A</strong> — Accountable: responsable último y quien aprueba.
        </div>
        <div>
          <strong>R</strong> — Responsible: ejecuta o coordina la actividad.
        </div>
        <div>
          <strong>C</strong> — Consulted: participa aportando conocimiento.
        </div>
        <div>
          <strong>I</strong> — Informed: debe mantenerse informado.
        </div>
      </div>

      <p className={styles.mnemonic}>
        Una frase sencilla para recordarlos: el Owner decide, el Steward organiza y supervisa, el Custodian implementa
        y el Consumer utiliza.
      </p>
    </div>
  );
}
