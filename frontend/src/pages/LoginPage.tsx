import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import styles from "./LoginPage.module.css";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(username, password);
      const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? "/";
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("No se pudo conectar con el servidor. Inténtalo de nuevo.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <aside className={styles.brandPanel}>
          <div className={styles.brandLogo}>Taidy</div>
          <div>
            <div className={styles.brandEyebrow}>Datos de negocio</div>
            <h1 className={styles.brandTitle}>Panel de datos</h1>
            <p className={styles.brandSubtitle}>
              Extracción y carga al datalake de Business Central y Factorial HR, sin depender de la terminal.
            </p>
          </div>
          <div className={styles.brandFooter}>
            <span className={styles.statusDot} aria-hidden="true" />
            Entorno de acceso restringido
          </div>
        </aside>

        <form className={styles.formPanel} onSubmit={handleSubmit} noValidate>
          <div>
            <div className={styles.formEyebrow}>Acceso de usuario</div>
            <h2 className={styles.formTitle}>Iniciar sesión</h2>
            <p className={styles.formSubtitle}>Introduce tu usuario local para acceder al panel.</p>
          </div>

          {error && (
            <div className={styles.errorBanner} role="alert">
              {error}
            </div>
          )}

          <div className={styles.field}>
            <label htmlFor="username">Usuario</label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>

          <div className={`${styles.field} ${styles.passwordRow}`}>
            <label htmlFor="password">Contraseña</label>
            <input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button
              type="button"
              className={styles.togglePassword}
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
            >
              {showPassword ? "Ocultar" : "Mostrar"}
            </button>
          </div>

          <button type="submit" className={styles.submit} disabled={isSubmitting}>
            {isSubmitting ? "Accediendo…" : "Acceder al panel"}
          </button>

          <div className={styles.footerNote}>Taidy · Panel de datos interno</div>
        </form>
      </div>
    </div>
  );
}
