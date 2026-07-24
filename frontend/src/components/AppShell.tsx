import { Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import styles from "./AppShell.module.css";

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.brand}>
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
      <main className={styles.content}>
        <Outlet />
      </main>
    </div>
  );
}
