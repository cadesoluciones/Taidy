import { useEffect, useState } from "react";
import { CheckCircle2, Clock, Lock } from "lucide-react";

import { ROLE_ADMIN, ROLE_OPERATOR, ROLE_READER, type Role } from "../../api/auth";
import { ApiError } from "../../api/client";
import { changeUserRole, createUser, deleteUser, fetchUsers, resetUserPassword, type ManagedUser } from "../../api/users";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import formStyles from "../../components/Form.module.css";
import styles from "./UsersPage.module.css";

const ROLE_OPTIONS: Role[] = [ROLE_READER, ROLE_OPERATOR, ROLE_ADMIN];

type PendingAction =
  | { kind: "delete"; username: string }
  | { kind: "role"; username: string; role: Role };

export function UsersPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [pendingRoles, setPendingRoles] = useState<Record<string, Role>>({});
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<Role>(ROLE_READER);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  async function reload() {
    const res = await fetchUsers();
    setUsers(res.items);
  }

  useEffect(() => {
    void reload();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreateSuccess(null);
    try {
      await createUser(newUsername, newPassword, newRole);
      setCreateSuccess(`Usuario '${newUsername.trim()}' creado. Deberá cambiar la contraseña en su primer login.`);
      setNewUsername("");
      setNewPassword("");
      setNewRole(ROLE_READER);
      await reload();
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "No se pudo crear el usuario.");
    }
  }

  async function confirmPendingAction() {
    if (!pendingAction) return;
    setIsBusy(true);
    try {
      if (pendingAction.kind === "delete") {
        await deleteUser(pendingAction.username);
      } else {
        await changeUserRole(pendingAction.username, pendingAction.role);
        setPendingRoles((prev) => {
          const next = { ...prev };
          delete next[pendingAction.username];
          return next;
        });
      }
      await reload();
    } finally {
      setIsBusy(false);
      setPendingAction(null);
    }
  }

  return (
    <section>
      <h1>Usuarios</h1>

      <h2>Crear usuario</h2>
      {createSuccess && <div className={formStyles.successBanner}>{createSuccess}</div>}
      {createError && <div className={formStyles.errorBanner}>{createError}</div>}
      <form className={formStyles.card} onSubmit={handleCreate}>
        <div className={formStyles.field}>
          <label htmlFor="new_username">Usuario</label>
          <input id="new_username" type="text" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} />
        </div>
        <div className={formStyles.field}>
          <label htmlFor="new_password">Contraseña temporal (mín. 8 caracteres)</label>
          <input
            id="new_password"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </div>
        <div className={formStyles.field}>
          <label htmlFor="new_role">Rol</label>
          <select id="new_role" value={newRole} onChange={(e) => setNewRole(e.target.value as Role)}>
            {ROLE_OPTIONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className={formStyles.submit}>
          Crear usuario
        </button>
      </form>

      <h2>Usuarios existentes</h2>
      {users.map((u) => {
        const pendingRole = pendingRoles[u.username];
        const showSave = pendingRole !== undefined && pendingRole !== u.role;
        const statusBits: Array<{ icon: typeof Clock; text: string }> = [];
        if (u.must_change_password) statusBits.push({ icon: Clock, text: "pendiente cambio de contraseña" });
        if (u.locked_until) statusBits.push({ icon: Lock, text: "bloqueado temporalmente" });

        return (
          <div className={styles.row} key={u.username}>
            <strong className={styles.name}>
              {u.username}
              {u.username === currentUser?.username && " (tú)"}
            </strong>
            <select
              className={styles.roleSelect}
              aria-label={`Rol de ${u.username}`}
              value={pendingRole ?? u.role}
              onChange={(e) => setPendingRoles((prev) => ({ ...prev, [u.username]: e.target.value as Role }))}
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            {showSave && (
              <button
                type="button"
                className={styles.btn}
                onClick={() => setPendingAction({ kind: "role", username: u.username, role: pendingRole })}
              >
                Guardar rol
              </button>
            )}
            <span className={styles.status}>
              {statusBits.length > 0 ? (
                statusBits.map(({ icon: Icon, text }, i) => (
                  <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 4, marginRight: 8 }}>
                    <Icon size={13} /> {text}
                  </span>
                ))
              ) : (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                  <CheckCircle2 size={13} color="var(--color-success)" /> activo
                </span>
              )}
            </span>
            <div className={styles.actions}>
              <button type="button" className={styles.btn} onClick={() => void resetUserPassword(u.username)}>
                Resetear contraseña
              </button>
              {u.username !== currentUser?.username && (
                <button
                  type="button"
                  className={styles.btnDanger}
                  onClick={() => setPendingAction({ kind: "delete", username: u.username })}
                >
                  Borrar
                </button>
              )}
            </div>
          </div>
        );
      })}

      <ConfirmDialog
        open={pendingAction !== null}
        title={pendingAction?.kind === "delete" ? "Borrar usuario" : "Cambiar rol"}
        description={
          pendingAction?.kind === "delete"
            ? `Vas a borrar definitivamente al usuario "${pendingAction.username}". No podrá volver a iniciar sesión y esta acción no se puede deshacer.`
            : pendingAction
              ? `Vas a cambiar el rol de "${pendingAction.username}" a "${pendingAction.role}". Esto cambia inmediatamente lo que esa persona puede hacer en la aplicación.`
              : ""
        }
        confirmLabel={pendingAction?.kind === "delete" ? "Borrar definitivamente" : "Confirmar cambio"}
        busy={isBusy}
        onConfirm={confirmPendingAction}
        onCancel={() => setPendingAction(null)}
      />
    </section>
  );
}
