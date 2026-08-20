import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowLeftRight,
  CalendarClock,
  ChevronDown,
  ChevronRight,
  Database,
  Download,
  GitFork,
  Home,
  History as HistoryIcon,
  KeyRound,
  LogOut,
  Menu,
  Network,
  Radar,
  Settings,
  Shuffle,
  ShieldCheck,
  Table2,
  Upload,
  UserCircle,
  Users,
  Workflow,
  X,
  type LucideIcon,
} from "lucide-react";
import { RefreshCw as Sync } from "lucide-react";

import { ROLE_ADMIN, ROLE_READER } from "../api/auth";
import { useAuth } from "../auth/AuthContext";
import { Modal } from "./Modal";
import styles from "./NavShell.module.css";
import { UserDirectory } from "./UserDirectory";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

const INICIO_SECTION: NavSection = { label: "", items: [{ to: "/", label: "Inicio", icon: Home }] };

// Reader's whole experience is Inicio (launch/follow their assigned
// workflows) + Cuenta -- these sections assume knowledge Reader isn't meant
// to need, and every route under them redirects Reader back to Inicio
// anyway (see RequireOperatorOrAdmin).
//
// "Sincronización" isn't in here -- its "Mapeos" item is Admin-only (it's a
// config action, like Conexiones API) while "Comparar" is Operator+Admin,
// so that one section's items are built per-role in NavShell() below instead
// of being a static list.
const OPERATIONAL_SECTIONS_BEFORE_SYNC: NavSection[] = [
  {
    label: "Actividad",
    items: [
      { to: "/actividad/tareas-en-curso", label: "Tareas en curso", icon: Activity },
      { to: "/actividad/historial", label: "Historial", icon: HistoryIcon },
    ],
  },
  {
    label: "Programación",
    items: [{ to: "/programacion", label: "Tareas programadas", icon: CalendarClock }],
  },
  { label: "Flujos", items: [{ to: "/flujos", label: "Flujos", icon: GitFork }] },
  {
    label: "Catálogo de datos",
    items: [
      { to: "/catalogo-datos", label: "Catálogo de datos", icon: Table2 },
      { to: "/catalogo-datos/gobernanza", label: "Gobernanza de datos", icon: Network },
      { to: "/catalogo-datos/impacto", label: "Análisis de impacto", icon: Radar },
    ],
  },
];

const OPERATIONAL_SECTIONS_AFTER_SYNC: NavSection[] = [
  {
    label: "Business Central",
    items: [
      { to: "/ejecutar/bc-extraer", label: "Extraer", icon: Download },
      { to: "/ejecutar/bc-subir", label: "Subir", icon: Upload },
      { to: "/ejecutar/bc-sync", label: "Sync", icon: Sync },
    ],
  },
  {
    label: "Factorial",
    items: [
      { to: "/ejecutar/factorial-extraer", label: "Extraer", icon: Download },
      { to: "/ejecutar/factorial-subir", label: "Subir", icon: Upload },
      { to: "/ejecutar/factorial-sync", label: "Sync", icon: Sync },
    ],
  },
  {
    label: "HubSpot",
    items: [
      { to: "/ejecutar/hubspot-extraer", label: "Extraer", icon: Download },
      { to: "/ejecutar/hubspot-subir", label: "Subir", icon: Upload },
      { to: "/ejecutar/hubspot-sync", label: "Sync", icon: Sync },
    ],
  },
  {
    label: "Fabric",
    items: [{ to: "/ejecutar/pipelines", label: "Pipelines", icon: Workflow }],
  },
];

const ADMIN_SECTION: NavSection = {
  label: "Administración",
  items: [
    { to: "/administracion/usuarios", label: "Usuarios", icon: Users },
    { to: "/administracion/conexiones-api", label: "Conexiones API", icon: Database },
    { to: "/administracion/claves-de-servicio", label: "Claves de servicio", icon: KeyRound },
    { to: "/administracion/auditoria", label: "Auditoría", icon: ShieldCheck },
    { to: "/administracion/configuracion", label: "Configuración", icon: Settings },
  ],
};

const ACCOUNT_SECTION: NavSection = {
  label: "Cuenta",
  items: [{ to: "/cuenta", label: "Mi cuenta", icon: UserCircle }],
};

// "Comparar" (Operator+Admin) and "Mapeos" (Admin-only) -- see
// OPERATIONAL_SECTIONS_BEFORE_SYNC's comment above for why this section
// isn't built statically. Both items are listed here (the superset, as if
// viewed by an admin) purely so collapse-state tracking below knows this
// section exists and which pages belong to it, regardless of who's logged in.
const SYNC_SECTION_ALL_ITEMS: NavSection = {
  label: "Sincronización",
  items: [
    { to: "/sincronizacion/comparar", label: "Comparar", icon: ArrowLeftRight },
    { to: "/sincronizacion/mapeos", label: "Mapeos", icon: Shuffle },
  ],
};

// Only sections with more than one link are worth collapsing -- a
// single-item "section" (Flujos, Fabric, Cuenta...) is really just a link
// with a heading, so there's nothing to hide by folding it.
const COLLAPSIBLE_SECTIONS = [
  ...OPERATIONAL_SECTIONS_BEFORE_SYNC,
  SYNC_SECTION_ALL_ITEMS,
  ...OPERATIONAL_SECTIONS_AFTER_SYNC,
  ADMIN_SECTION,
].filter((s) => s.items.length > 1);

const NAV_COLLAPSE_STORAGE_KEY = "taidy.nav.collapsedSections";

function sectionLabelContaining(pathname: string): string | null {
  for (const section of COLLAPSIBLE_SECTIONS) {
    if (section.items.some((item) => item.to === pathname)) return section.label;
  }
  return null;
}

// First-ever visit (nothing in localStorage yet): collapse every
// collapsible section except the one holding the current page, so the menu
// starts short instead of dumping every sub-item down the sidebar at once.
function loadCollapsedSections(activeLabel: string | null): Set<string> {
  try {
    const raw = localStorage.getItem(NAV_COLLAPSE_STORAGE_KEY);
    if (raw) return new Set(JSON.parse(raw) as string[]);
  } catch {
    // Malformed/unavailable storage -- fall through to the default below.
  }
  return new Set(COLLAPSIBLE_SECTIONS.map((s) => s.label).filter((label) => label !== activeLabel));
}

function persistCollapsedSections(labels: Set<string>): void {
  try {
    localStorage.setItem(NAV_COLLAPSE_STORAGE_KEY, JSON.stringify([...labels]));
  } catch {
    // Best-effort only -- a failed write just means the choice won't survive reload.
  }
}

function breadcrumbFor(sections: NavSection[], pathname: string): string {
  for (const section of sections) {
    for (const item of section.items) {
      if (item.to === pathname) {
        return section.label ? `${section.label} · ${item.label}` : item.label;
      }
    }
  }
  return "Panel de datos";
}

export function NavShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [showUserModal, setShowUserModal] = useState(false);
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(() =>
    loadCollapsedSections(sectionLabelContaining(location.pathname)),
  );

  // Close the mobile drawer automatically on navigation -- otherwise it
  // stays open over the newly-loaded page.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  // Navigating into a page whose section is currently folded (e.g. via the
  // "Gestionar tablas" link from an Ejecutar form) should reveal it -- a
  // collapsed group hiding the page you're actually on would be confusing.
  useEffect(() => {
    const label = sectionLabelContaining(location.pathname);
    if (!label) return;
    setCollapsedSections((prev) => {
      if (!prev.has(label)) return prev;
      const next = new Set(prev);
      next.delete(label);
      persistCollapsedSections(next);
      return next;
    });
  }, [location.pathname]);

  function toggleSection(label: string) {
    setCollapsedSections((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      persistCollapsedSections(next);
      return next;
    });
  }

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const isReader = user?.role === ROLE_READER;
  const isAdmin = user?.role === ROLE_ADMIN;
  const syncSection: NavSection = {
    label: "Sincronización",
    items: isAdmin
      ? SYNC_SECTION_ALL_ITEMS.items
      : SYNC_SECTION_ALL_ITEMS.items.filter((i) => i.to !== "/sincronizacion/mapeos"),
  };
  const sections = [
    INICIO_SECTION,
    ...(isReader
      ? []
      : [...OPERATIONAL_SECTIONS_BEFORE_SYNC, syncSection, ...OPERATIONAL_SECTIONS_AFTER_SYNC]),
    ...(isAdmin ? [ADMIN_SECTION] : []),
    ACCOUNT_SECTION,
  ];
  const breadcrumb = breadcrumbFor(sections, location.pathname);

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <button
            type="button"
            className={styles.menuToggle}
            aria-label={mobileNavOpen ? "Cerrar menú" : "Abrir menú"}
            aria-expanded={mobileNavOpen}
            onClick={() => setMobileNavOpen((v) => !v)}
          >
            {mobileNavOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <span className={styles.brandName}>NEXUS-BDB</span>
          <span className={styles.pageTitle}>{breadcrumb}</span>
        </div>
        <div className={styles.right}>
          <span className={styles.liveStatus}>
            <span className={styles.liveDot} aria-hidden="true" />
            Tiempo real
          </span>
          {user?.role === ROLE_ADMIN && (
            <button
              type="button"
              className={styles.iconButton}
              aria-label="Gestión de usuarios"
              title="Gestión de usuarios"
              onClick={() => setShowUserModal(true)}
            >
              <Users size={17} />
            </button>
          )}
          {user && (
            <div className={styles.identity}>
              <span className={styles.avatar} aria-hidden="true">
                {user.username.slice(0, 1).toUpperCase()}
              </span>
              <span className={styles.identityText}>
                {user.username}
                <br />
                <span className={styles.identityRole}>{user.role}</span>
              </span>
            </div>
          )}
          <button type="button" className={styles.logoutButton} onClick={handleLogout}>
            <LogOut size={14} />
            Cerrar sesión
          </button>
        </div>
      </header>
      <div
        className={`${styles.backdrop} ${mobileNavOpen ? styles.backdropVisible : ""}`}
        onClick={() => setMobileNavOpen(false)}
        aria-hidden="true"
      />
      <nav
        className={`${styles.sidebar} ${mobileNavOpen ? styles.sidebarOpen : ""}`}
        aria-label="Navegación principal"
      >
        {sections.map((section) => {
          const collapsible = section.items.length > 1;
          const isCollapsed = collapsible && collapsedSections.has(section.label);
          const panelId = `nav-section-${section.label.replace(/\s+/g, "-").toLowerCase()}`;
          return (
            <div key={section.label || "inicio"}>
              {section.label && collapsible && (
                <button
                  type="button"
                  className={styles.sectionToggle}
                  aria-expanded={!isCollapsed}
                  aria-controls={panelId}
                  onClick={() => toggleSection(section.label)}
                >
                  {section.label}
                  {isCollapsed ? (
                    <ChevronRight size={13} className={styles.sectionChevron} aria-hidden="true" />
                  ) : (
                    <ChevronDown size={13} className={styles.sectionChevron} aria-hidden="true" />
                  )}
                </button>
              )}
              {section.label && !collapsible && <div className={styles.sectionLabel}>{section.label}</div>}
              {!isCollapsed && (
                <div id={panelId}>
                  {section.items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end
                      className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ""}`}
                    >
                      <item.icon size={16} aria-hidden="true" />
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      <main className={styles.content}>
        <Outlet />
      </main>
      {user?.role === ROLE_ADMIN && (
        <Modal
          open={showUserModal}
          eyebrow="Control de acceso"
          title="Gestión de usuarios"
          subtitle="Administra operadores, permisos y credenciales de la cuenta."
          onClose={() => setShowUserModal(false)}
        >
          {showUserModal && <UserDirectory />}
        </Modal>
      )}
    </div>
  );
}
