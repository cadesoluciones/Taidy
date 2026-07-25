import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  CalendarClock,
  Database,
  Download,
  GitFork,
  Home,
  History as HistoryIcon,
  LogOut,
  Menu,
  ShieldCheck,
  Upload,
  UserCircle,
  Users,
  Workflow,
  X,
  type LucideIcon,
} from "lucide-react";
import { RefreshCw as Sync } from "lucide-react";

import { ROLE_ADMIN } from "../api/auth";
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

const BASE_SECTIONS: NavSection[] = [
  { label: "", items: [{ to: "/", label: "Inicio", icon: Home }] },
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
    label: "Fabric",
    items: [{ to: "/ejecutar/pipelines", label: "Pipelines", icon: Workflow }],
  },
];

const ADMIN_SECTION: NavSection = {
  label: "Administración",
  items: [
    { to: "/administracion/usuarios", label: "Usuarios", icon: Users },
    { to: "/administracion/conexiones-api", label: "Conexiones API", icon: Database },
    { to: "/administracion/auditoria", label: "Auditoría", icon: ShieldCheck },
  ],
};

const ACCOUNT_SECTION: NavSection = {
  label: "Cuenta",
  items: [{ to: "/cuenta", label: "Mi cuenta", icon: UserCircle }],
};

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

  // Close the mobile drawer automatically on navigation -- otherwise it
  // stays open over the newly-loaded page.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const sections = [...BASE_SECTIONS, ...(user?.role === ROLE_ADMIN ? [ADMIN_SECTION] : []), ACCOUNT_SECTION];
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
          <span className={styles.brandName}>Taidy</span>
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
        {sections.map((section) => (
          <div key={section.label || "inicio"}>
            {section.label && <div className={styles.sectionLabel}>{section.label}</div>}
            {section.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ""}`}
              >
                <item.icon size={16} aria-hidden="true" />
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
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
