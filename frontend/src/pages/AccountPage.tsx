import { useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import formStyles from "../components/Form.module.css";

export function AccountPage() {
  const { user, changePassword } = useAuth();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSuccess(null);
    setError(null);
    setIsSubmitting(true);
    try {
      await changePassword(newPassword, confirmPassword);
      setSuccess("Contraseña actualizada.");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar la contraseña.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section>
      <h1>Mi cuenta</h1>
      <p>
        Sesión iniciada como <strong>{user?.username}</strong> — rol: {user?.role}
      </p>
      <h2>Cambiar mi contraseña</h2>
      {success && <div className={formStyles.successBanner}>{success}</div>}
      {error && <div className={formStyles.errorBanner}>{error}</div>}
      <form className={formStyles.card} onSubmit={handleSubmit}>
        <div className={formStyles.field}>
          <label htmlFor="new_password">Nueva contraseña</label>
          <input
            id="new_password"
            type="password"
            minLength={8}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
        </div>
        <div className={formStyles.field}>
          <label htmlFor="confirm_password">Confirma la nueva contraseña</label>
          <input
            id="confirm_password"
            type="password"
            minLength={8}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />
        </div>
        <button type="submit" className={formStyles.submit} disabled={isSubmitting}>
          {isSubmitting ? "Guardando…" : "Guardar nueva contraseña"}
        </button>
      </form>
    </section>
  );
}
