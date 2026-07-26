import { useEffect, useState } from "react";
import { CheckCircle2, Clock, Lock, Plus } from "lucide-react";

import { ROLE_ADMIN, ROLE_OPERATOR, ROLE_READER, type Role } from "../api/auth";
import { ApiError } from "../api/client";
import {
  changeUserRole,
  createUser,
  deleteUser,
  fetchUsers,
  fetchUserSessions,
  resetUserPassword,
  revokeUserSession,
  type ManagedUser,
  type UserSession,
} from "../api/users";
import { useAuth } from "../auth/AuthContext";
import { ConfirmDialog } from "./ConfirmDialog";
import formStyles from "./Form.module.css";
import styles from "./UserDirectory.module.css";

const ROLE_OPTIONS: Role[] = [ROLE_READER, ROLE_OPERATOR, ROLE_ADMIN];

type PendingAction = { kind: "delete"; username: string } | { kind: "role"; username: string; role: Role };

/** Master/detail user management: a directory list (left) and a detail
 * editor for the selected account (right) -- used both as the content of
 * /administracion/usuarios and inside the header's "Gestión de usuarios"
 * dialog, so the two entry points never duplicate this logic. */
export function UserDirectory() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [selectedUsername, setSelectedUsername] = useState<string | null>(null);
  const [roleDraft, setRoleDraft] = useState<Role | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [resetNotice, setResetNotice] = useState<string | null>(null);
  const [sessions, setSessions] = useState<UserSession[]>([]);

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<Role>(ROLE_READER);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  async function reload() {
    const res = await fetchUsers();
    setUsers(res.items);
    return res.items;
  }

  useEffect(() => {
    reload().then((items) => {
      const first = items[0];
      if (first && !selectedUsername) setSelectedUsername(first.username);
    });
    // Only on mount -- selection afterwards is user-driven.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedUser = users.find((u) => u.username === selectedUsername) ?? null;

  useEffect(() => {
    setRoleDraft(selectedUser?.role ?? null);
    setResetNotice(null);
  }, [selectedUser?.username, selectedUser?.role]);

  async function reloadSessions(username: string) {
    setSessions((await fetchUserSessions(username)).items);
  }

  useEffect(() => {
    setSessions([]);
    if (selectedUser) void reloadSessions(selectedUser.username);
    // Only re-fetch when the selected account changes, not on every role edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedUser?.username]);

  async function handleRevokeSession(sessionRef: string) {
    if (!selectedUser) return;
    await revokeUserSession(selectedUser.username, sessionRef);
    await reloadSessions(selectedUser.username);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreateSuccess(null);
    try {
      const created = await createUser(newUsername, newPassword, newRole);
      setCreateSuccess(`Usuario '${created.username}' creado. Deberá cambiar la contraseña en su primer login.`);
      setNewUsername("");
      setNewPassword("");
      setNewRole(ROLE_READER);
      setShowCreateForm(false);
      await reload();
      setSelectedUsername(created.username);
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "No se pudo crear el usuario.");
    }
  }

  async function saveRole() {
    if (!selectedUser || !roleDraft || roleDraft === selectedUser.role) return;
    setPendingAction({ kind: "role", username: selectedUser.username, role: roleDraft });
  }

  async function confirmPendingAction() {
    if (!pendingAction) return;
    setIsBusy(true);
    try {
      if (pendingAction.kind === "delete") {
        await deleteUser(pendingAction.username);
        if (selectedUsername === pendingAction.username) setSelectedUsername(null);
      } else {
        await changeUserRole(pendingAction.username, pendingAction.role);
      }
      await reload();
    } finally {
      setIsBusy(false);
      setPendingAction(null);
    }
  }

  async function handleResetPassword() {
    if (!selectedUser) return;
    await resetUserPassword(selectedUser.username);
    setResetNotice("Se ha solicitado el cambio: deberá fijar una nueva contraseña en su próximo inicio de sesión.");
    await reload();
  }

  const statusBits: Array<{ icon: typeof Clock; text: string }> = [];
  if (selectedUser?.must_change_password) statusBits.push({ icon: Clock, text: "pendiente cambio de contraseña" });
  if (selectedUser?.locked_until) statusBits.push({ icon: Lock, text: "bloqueado temporalmente" });

  return (
    <div className={styles.layout}>
      <div className={styles.directory}>
        <div className={styles.directoryHeader}>
          <div>
            <div className={styles.eyebrow}>Directorio</div>
            <div className={styles.count}>{users.length} usuario{users.length === 1 ? "" : "s"}</div>
          </div>
          <button
            type="button"
            className={styles.addButton}
            aria-label="Nuevo usuario"
            onClick={() => setShowCreateForm((v) => !v)}
          >
            <Plus size={16} />
          </button>
        </div>

        {createSuccess && <div className={formStyles.successBanner}>{createSuccess}</div>}

        {showCreateForm && (
          <form className={styles.createForm} onSubmit={handleCreate}>
            {createError && <div className={formStyles.errorBanner}>{createError}</div>}
            <div className={formStyles.field}>
              <label htmlFor="ud_new_username">Usuario</label>
              <input id="ud_new_username" type="text" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} />
            </div>
            <div className={formStyles.field}>
              <label htmlFor="ud_new_password">Contraseña temporal (mín. 8 caracteres)</label>
              <input
                id="ud_new_password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div className={formStyles.field}>
              <label htmlFor="ud_new_role">Rol</label>
              <select id="ud_new_role" value={newRole} onChange={(e) => setNewRole(e.target.value as Role)}>
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
        )}

        <ul className={styles.list}>
          {users.map((u) => (
            <li key={u.username}>
              <button
                type="button"
                className={`${styles.row} ${u.username === selectedUsername ? styles.rowActive : ""}`}
                onClick={() => setSelectedUsername(u.username)}
              >
                <span className={styles.avatar} aria-hidden="true">
                  {u.username.slice(0, 1).toUpperCase()}
                </span>
                <span className={styles.rowText}>
                  <span className={styles.rowName}>
                    {u.username}
                    {u.username === currentUser?.username && " (tú)"}
                  </span>
                  <span className={styles.rowRole}>{u.role}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className={styles.detail}>
        {!selectedUser ? (
          <p className={styles.emptyState}>Selecciona un usuario del directorio para ver o editar su cuenta.</p>
        ) : (
          <>
            <div className={styles.eyebrow}>Cuenta seleccionada</div>
            <h3 className={styles.detailName}>{selectedUser.username}</h3>

            <div className={formStyles.grid}>
              <div className={formStyles.field}>
                <label htmlFor="ud_username">Usuario</label>
                <input id="ud_username" type="text" value={selectedUser.username} disabled />
              </div>
              <div className={formStyles.field}>
                <label htmlFor="ud_role">Rol</label>
                <select
                  id="ud_role"
                  value={roleDraft ?? selectedUser.role}
                  onChange={(e) => setRoleDraft(e.target.value as Role)}
                >
                  {ROLE_OPTIONS.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className={styles.stateRow}>
              {statusBits.length > 0 ? (
                statusBits.map(({ icon: Icon, text }, i) => (
                  <span key={i} className={styles.stateBit}>
                    <Icon size={13} /> {text}
                  </span>
                ))
              ) : (
                <span className={styles.stateBit}>
                  <CheckCircle2 size={13} color="var(--color-success)" /> cuenta activa
                </span>
              )}
            </div>

            <button
              type="button"
              className={formStyles.submit}
              disabled={roleDraft === selectedUser.role}
              onClick={() => void saveRole()}
            >
              Guardar cambios
            </button>

            <div className={styles.securitySection}>
              <div className={styles.eyebrow}>Seguridad</div>
              {resetNotice && <div className={formStyles.successBanner}>{resetNotice}</div>}
              <div className={styles.securityRow}>
                <span>Forzar cambio de contraseña en el próximo inicio de sesión.</span>
                <button type="button" className={styles.btn} onClick={() => void handleResetPassword()}>
                  Solicitar cambio
                </button>
              </div>
              {selectedUser.username !== currentUser?.username && (
                <div className={styles.securityRow}>
                  <span>Eliminar esta cuenta definitivamente.</span>
                  <button
                    type="button"
                    className={styles.btnDanger}
                    onClick={() => setPendingAction({ kind: "delete", username: selectedUser.username })}
                  >
                    Eliminar usuario
                  </button>
                </div>
              )}

              <div className={styles.sessionsSection}>
                <span className={styles.sessionsLabel}>Sesiones activas</span>
                {sessions.length === 0 ? (
                  <p className={styles.emptySessions}>Sin sesiones activas.</p>
                ) : (
                  <ul className={styles.sessionsList}>
                    {sessions.map((s) => (
                      <li key={s.session_ref} className={styles.sessionRow}>
                        <span className={styles.sessionMeta}>Iniciada: {s.created_at}</span>
                        <button
                          type="button"
                          className={styles.btnDanger}
                          onClick={() => void handleRevokeSession(s.session_ref)}
                        >
                          Revocar sesión
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </>
        )}
      </div>

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
    </div>
  );
}
