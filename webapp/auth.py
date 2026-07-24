# -*- coding: utf-8 -*-
"""
Local username/password authentication for the Taidy webapp.

No external identity provider: credentials live in webapp/users_db.py
(SQLite, bcrypt-hashed passwords, per-user lockout after repeated failures).

Session is plain st.session_state — no persistent cookie. A page refresh or
a new tab requires logging in again. This is a deliberate simplification:
an earlier version used streamlit-cookies-manager for a "stay logged in"
persistent cookie, but that (unmaintained) library caused two real bugs in
practice (a StreamlitDuplicateElementKey collision, and an unreliable
fire-and-forget cookie save that made "cerrar sesión" unreliable). Trading
persistence away removes that whole class of bugs; if persistence is wanted
back later, it needs a library that's actually verifiable without a live
browser, not this one.

The role-gating API below (has_role / check_role / check_any_role /
require_role / require_any_role / ROLES_*) is unchanged from the previous
versions — webapp/app.py doesn't need to change how it gates actions.

Audit log (webapp/audit.log, gitignored): one JSON line per auth-relevant
event (login, logout, access denied, password change). Never contains
passwords or password hashes.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import streamlit as st

from webapp import users_db
from webapp.users_db import ROLE_ADMIN, ROLE_OPERATOR, ROLE_READER  # re-exported for app.py

ROLES_READ = [ROLE_READER, ROLE_OPERATOR, ROLE_ADMIN]
ROLES_OPERATE = [ROLE_OPERATOR, ROLE_ADMIN]
ROLES_ADMIN = [ROLE_ADMIN]

_AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit.log"
_AUDIT_LOCK = threading.Lock()

users_db.init_db()


# --------------------------------------------------------------------------------------
# Audit log — security events only (not business run history, see history.py)
# --------------------------------------------------------------------------------------


def _audit(event: str, outcome: str, *, user: str = "-", detail: str = "") -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "outcome": outcome,
        "user": user,
        "detail": detail,
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _AUDIT_LOCK:
        with _AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def get_audit_log(limit: int = 200) -> List[dict]:
    if not _AUDIT_LOG_PATH.exists():
        return []
    lines = _AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(entries))


# --------------------------------------------------------------------------------------
# Current-user helpers
# --------------------------------------------------------------------------------------


def is_authenticated() -> bool:
    return "auth_user" in st.session_state


def get_current_user() -> str:
    if not is_authenticated():
        return "anónimo"
    return st.session_state["auth_user"]["username"]


def get_current_roles() -> List[str]:
    if not is_authenticated():
        return []
    role = st.session_state["auth_user"].get("role")
    return [role] if role else []


def has_role(role: str) -> bool:
    return role in get_current_roles()


def do_logout() -> None:
    """Use as a button's on_click. Plain session_state clear — no cookie involved."""
    username = get_current_user()
    _audit("logout", "ok", user=username)
    st.session_state.pop("auth_user", None)
    st.session_state.pop("_auth_login_audited", None)


# --------------------------------------------------------------------------------------
# Login / change-password forms
# --------------------------------------------------------------------------------------


def _render_login_form() -> None:
    st.title("Taidy — Panel de datos")
    st.write("Inicia sesión con tu usuario local.")
    with st.form("login_form"):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Iniciar sesión", type="primary")

    if not submitted:
        return

    result = users_db.verify_login(username, password)
    if not result.ok:
        _audit("login", "denied", user=username or "-", detail=result.reason)
        if result.reason.startswith("locked out"):
            st.error(
                f"Cuenta bloqueada temporalmente tras {users_db.MAX_FAILED_ATTEMPTS} intentos fallidos. "
                f"Inténtalo de nuevo en unos minutos."
            )
        else:
            st.error("Usuario o contraseña incorrectos.")
        return

    st.session_state["auth_user"] = {"username": result.username, "role": result.role}
    st.rerun()


def render_change_password_form(*, force: bool) -> None:
    """Forced (blocks everything else) when force=True, otherwise a normal form
    usable from a "Mi cuenta"-style section for a voluntary password change.
    """
    user_before = get_current_user()
    if force:
        st.title("Taidy — Panel de datos")
        st.warning("Debes establecer una contraseña nueva antes de continuar.")

    with st.form(f"change_password_form_{force}"):
        new_password = st.text_input("Nueva contraseña", type="password")
        confirm = st.text_input("Confirma la nueva contraseña", type="password")
        submitted = st.form_submit_button("Guardar nueva contraseña")

    if not submitted:
        return

    if new_password != confirm:
        st.error("Las contraseñas no coinciden.")
        return
    try:
        users_db.change_password(user_before, new_password, must_change_password=False)
    except ValueError as exc:
        st.error(str(exc))
        return

    _audit("password_change", "ok", user=user_before)
    st.session_state["auth_user"]["role"] = users_db.get_user(user_before)["role"]
    st.success("Contraseña actualizada.")
    if force:
        st.rerun()


# --------------------------------------------------------------------------------------
# Gates — call at the top of app.py / before any gated action
# --------------------------------------------------------------------------------------


def deny(message: str) -> None:
    """Hard denial: shows the message and stops the ENTIRE script (see require_role)."""
    st.error(f"🚫 Acceso denegado. {message}")
    st.stop()


def require_authenticated_user() -> None:
    """Blocks anonymous access and enforces a pending forced password change.

    Call this once at the very top of app.py before rendering anything else.
    """
    if "auth_user" not in st.session_state:
        _render_login_form()
        st.stop()
        return

    username = get_current_user()

    if not st.session_state.get("_auth_login_audited"):
        st.session_state["_auth_login_audited"] = True
        _audit("login", "ok", user=username)

    current = users_db.get_user(username)
    if current is None:
        st.session_state.pop("auth_user", None)
        st.session_state.pop("_auth_login_audited", None)
        deny("Tu usuario ya no existe. Inicia sesión de nuevo.")
        return

    st.session_state["auth_user"]["role"] = current["role"]  # keep role fresh across the session

    if current["must_change_password"]:
        render_change_password_form(force=True)
        st.stop()
        return


def require_role(role: str) -> None:
    """Hard gate: stops rendering the ENTIRE script if unmet. Streamlit reruns the whole
    page top-to-bottom, so st.stop() here also skips any tabs/sections defined after this
    call — use only for the single top-of-page gate, never inside a specific tab/button.
    """
    require_authenticated_user()
    if not has_role(role):
        _audit("authorization", "denied", user=get_current_user(), detail=f"missing role {role}")
        deny(f"Esta acción requiere el rol '{role}'.")


def require_any_role(roles: List[str]) -> None:
    require_authenticated_user()
    if not any(has_role(r) for r in roles):
        _audit("authorization", "denied", user=get_current_user(), detail=f"missing any of {roles}")
        deny(f"Esta acción requiere alguno de estos roles: {', '.join(roles)}.")


def check_role(role: str) -> bool:
    """Soft check for gating one tab/action: returns bool, never stops the script.
    The backend re-check the user cannot bypass by hiding a button — but denying it
    must not blank out the rest of the page, so the caller renders its own st.error().
    """
    ok = has_role(role)
    if not ok:
        _audit("authorization", "denied", user=get_current_user(), detail=f"missing role {role}")
    return ok


def check_any_role(roles: List[str]) -> bool:
    ok = any(has_role(r) for r in roles)
    if not ok:
        _audit("authorization", "denied", user=get_current_user(), detail=f"missing any of {roles}")
    return ok
