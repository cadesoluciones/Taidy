# -*- coding: utf-8 -*-
"""
Local username/password user store (SQLite), used by webapp/auth.py.

Passwords are hashed with bcrypt — never stored or logged in plain text.
Failed logins are throttled per-username (lockout) to slow down brute force.
Roles reuse the same App.Reader / App.Operator / App.Admin values used
throughout the rest of the app (webapp/auth.py's ROLE_* constants).
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import bcrypt

from webapp.state_dir import state_path

_DB_PATH = state_path("users.db", Path(__file__).resolve().parent)
_LOCK = threading.Lock()

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 5

ROLE_READER = "App.Reader"
ROLE_OPERATOR = "App.Operator"
ROLE_ADMIN = "App.Admin"
VALID_ROLES = {ROLE_READER, ROLE_OPERATOR, ROLE_ADMIN}

DEFAULT_ADMIN_USERNAME = "admin"
# Fixed, known default per explicit request — mitigated by must_change_password,
# which blocks all access until the password is changed on first login.
DEFAULT_ADMIN_PASSWORD = "changeme"


@contextmanager
def _connect():
    with _LOCK:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db() -> None:
    """Creates the table if missing and seeds the default admin if the store is empty.
    Call once at app startup (idempotent — safe to call on every process start).
    """
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
    _ensure_default_admin()


def _ensure_default_admin() -> None:
    with _connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count > 0:
            return
        conn.execute(
            "INSERT INTO users (username, password_hash, role, must_change_password, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (
                DEFAULT_ADMIN_USERNAME,
                _hash_password(DEFAULT_ADMIN_PASSWORD),
                ROLE_ADMIN,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


class LoginResult:
    def __init__(
        self,
        ok: bool,
        *,
        username: str = "",
        role: str = "",
        must_change_password: bool = False,
        reason: str = "",
    ) -> None:
        self.ok = ok
        self.username = username
        self.role = role
        self.must_change_password = must_change_password
        self.reason = reason  # audit-log detail only — never shown verbatim to the end user


def verify_login(username: str, password: str) -> LoginResult:
    username = username.strip()
    if not username or not password:
        return LoginResult(False, reason="empty credentials")

    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            return LoginResult(False, reason="unknown user")

        if row["locked_until"]:
            locked_until = datetime.fromisoformat(row["locked_until"])
            if locked_until > datetime.now(timezone.utc):
                return LoginResult(False, reason="locked out")
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?", (username,)
            )

        if not _verify_password(password, row["password_hash"]):
            new_failed = row["failed_attempts"] + 1
            locked_until = None
            if new_failed >= MAX_FAILED_ATTEMPTS:
                locked_until = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
            conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE username = ?",
                (new_failed, locked_until, username),
            )
            reason = "locked out (too many attempts)" if locked_until else "bad password"
            return LoginResult(False, reason=reason)

        conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?", (username,))
        return LoginResult(
            True,
            username=row["username"],
            role=row["role"],
            must_change_password=bool(row["must_change_password"]),
        )


def get_user(username: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT username, role, must_change_password FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def list_users() -> List[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT username, role, must_change_password, failed_attempts, locked_until, created_at "
            "FROM users ORDER BY username"
        ).fetchall()
        return [dict(r) for r in rows]


def create_user(username: str, password: str, role: str, *, must_change_password: bool = True) -> None:
    username = username.strip()
    if not username:
        raise ValueError("El nombre de usuario no puede estar vacío.")
    if role not in VALID_ROLES:
        raise ValueError(f"Rol desconocido: {role}")
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    with _connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise ValueError(f"El usuario '{username}' ya existe.")
        conn.execute(
            "INSERT INTO users (username, password_hash, role, must_change_password, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                username,
                _hash_password(password),
                role,
                int(must_change_password),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def set_role(username: str, role: str) -> None:
    if role not in VALID_ROLES:
        raise ValueError(f"Rol desconocido: {role}")
    with _connect() as conn:
        admins = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = ?", (ROLE_ADMIN,)).fetchone()["n"]
        current = conn.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
        if current and current["role"] == ROLE_ADMIN and role != ROLE_ADMIN and admins <= 1:
            raise ValueError("No puedes quitarle el rol Admin al último administrador.")
        conn.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))


def delete_user(username: str) -> None:
    with _connect() as conn:
        admins = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = ?", (ROLE_ADMIN,)).fetchone()["n"]
        target = conn.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
        if target and target["role"] == ROLE_ADMIN and admins <= 1:
            raise ValueError("No puedes borrar el último administrador.")
        conn.execute("DELETE FROM users WHERE username = ?", (username,))


def change_password(username: str, new_password: str, *, must_change_password: bool = False) -> None:
    if len(new_password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = ?, failed_attempts = 0, locked_until = NULL "
            "WHERE username = ?",
            (_hash_password(new_password), int(must_change_password), username),
        )


def force_password_reset(username: str) -> None:
    """Admin action: the user must set a new password on their next login."""
    with _connect() as conn:
        conn.execute("UPDATE users SET must_change_password = 1 WHERE username = ?", (username,))
