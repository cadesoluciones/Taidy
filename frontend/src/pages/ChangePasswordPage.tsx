import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import styles from "./ChangePasswordPage.module.css";

/** Mirrors auth.render_change_password_form(force=...): forced when the
 * session says must_change_password, otherwise reachable voluntarily from
 * "Mi cuenta" once ForcedPasswordChange's own guard has passed.
 */
export function ChangePasswordPage() {
  const { user, changePassword } = useAuth();
  const navigate = useNavigate();
  const force = Boolean(user?.must_change_password);

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await changePassword(newPassword, confirmPassword);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar la contraseña.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <h2>Cambiar contraseña</h2>
        {force && (
          <p className={styles.warning}>Debes establecer una contraseña nueva antes de continuar.</p>
        )}
        {error && <div className={styles.errorBanner}>{error}</div>}
        <form onSubmit={handleSubmit} noValidate>
          <div className={styles.field}>
            <label htmlFor="new_password">Nueva contraseña</label>
            <input
              id="new_password"
              type="password"
              minLength={8}
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="confirm_password">Confirma la nueva contraseña</label>
            <input
              id="confirm_password"
              type="password"
              minLength={8}
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" className={styles.submit} disabled={isSubmitting}>
            {isSubmitting ? "Guardando…" : "Guardar nueva contraseña"}
          </button>
        </form>
      </div>
    </div>
  );
}
