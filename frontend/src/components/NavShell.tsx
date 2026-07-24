import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { ROLE_ADMIN } from "../api/auth";
import { useAuth } from "../auth/AuthContext";
import styles from "./NavShell.module.css";

interface NavItem {
  to: string;
  label: string;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

const BASE_SECTIONS: NavSection[] = [
  { label: "", items: [{ to: "/", label: "Inicio" }] },
  {
    label: "Ejecutar",
    items: [
      { to: "/ejecutar/bc-extraer", label: "BC · Extraer" },
      { to: "/ejecutar/bc-subir", label: "BC · Subir" },
      { to: "/ejecutar/bc-sync", label: "BC · Sync" },
      { to: "/ejecutar/factorial-extraer", label: "Factorial · Extraer" },
      { to: "/ejecutar/factorial-subir", label: "Factorial · Subir" },
      { to: "/ejecutar/factorial-sync", label: "Factorial · Sync" },
      { to: "/ejecutar/pipelines", label: "Fabric · Pipelines" },
    ],
  },
  { label: "Flujos", items: [{ to: "/flujos", label: "Flujos" }] },
  { label: "Programación", items: [{ to: "/programacion", label: "Tareas programadas" }] },
  {
    label: "Actividad",
    items: [
      { to: "/actividad/tareas-en-curso", label: "Tareas en curso" },
      { to: "/actividad/historial", label: "Historial" },
    ],
  },
];

const ADMIN_SECTION: NavSection = {
  label: "Administración",
  items: [
    { to: "/administracion/usuarios", label: "Usuarios" },
    { to: "/administracion/auditoria", label: "Auditoría" },
  ],
};

const ACCOUNT_SECTION: NavSection = { label: "Cuenta", items: [{ to: "/cuenta", label: "Mi cuenta" }] };

export function NavShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

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
            ☰
          </button>
          <span className={styles.brandName}>Taidy</span>
          <span className={styles.pageTitle}>Panel de datos</span>
        </div>
        <div className={styles.right}>
          <span className={styles.liveStatus}>
            <span className={styles.liveDot} aria-hidden="true" />
            Tiempo real
          </span>
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
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <main className={styles.content}>
        <Outlet />
      </main>
    </div>
  );
}
