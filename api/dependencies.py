# -*- coding: utf-8 -*-
"""
Session store and FastAPI auth dependencies.

Mirrors webapp/auth.py's model exactly (never trust a cached client claim
about role; re-check server-side on every request) but adapted to REST:
Streamlit could cache the role in st.session_state for a whole script run;
here every request is independent, so the current role/must_change_password
is re-read from users_db fresh each time -- the session only remembers WHO
is asking, not what they're allowed to do.

The session store is an in-memory dict, the same pattern already used by
webapp/tasks.py's task registry and webapp/workflow_engine.py's run registry
-- consistent with this project's existing style, and appropriate here since
neither the Streamlit app's st.session_state nor a signed-cookie session
needs to survive a server restart.
"""

from __future__ import annotations

import secrets
import threading
from typing import Dict, List, Optional

from fastapi import Cookie, Depends, HTTPException, status

from webapp import users_db

SESSION_COOKIE_NAME = "taidy_session"

_SESSIONS: Dict[str, str] = {}  # session_id -> username
_SESSIONS_LOCK = threading.Lock()


def create_session(username: str) -> str:
    session_id = secrets.token_urlsafe(32)
    with _SESSIONS_LOCK:
        _SESSIONS[session_id] = username
    return session_id


def get_session_username(session_id: Optional[str]) -> Optional[str]:
    if not session_id:
        return None
    with _SESSIONS_LOCK:
        return _SESSIONS.get(session_id)


def destroy_session(session_id: Optional[str]) -> None:
    if not session_id:
        return
    with _SESSIONS_LOCK:
        _SESSIONS.pop(session_id, None)


class CurrentUser:
    def __init__(self, username: str, role: str, must_change_password: bool) -> None:
        self.username = username
        self.role = role
        self.must_change_password = must_change_password


def get_current_user_allow_pending(
    taidy_session: Optional[str] = Cookie(default=None),
) -> CurrentUser:
    """Resolves the caller's identity WITHOUT blocking on a pending forced
    password change -- only /auth/me and /auth/change-password should use
    this directly; everything else should depend on get_current_user below.
    """
    username = get_session_username(taidy_session)
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado.")

    row = users_db.get_user(username)
    if row is None:
        destroy_session(taidy_session)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tu usuario ya no existe. Inicia sesión de nuevo.",
        )
    return CurrentUser(
        username=row["username"],
        role=row["role"],
        must_change_password=bool(row["must_change_password"]),
    )


def get_current_user(
    user: CurrentUser = Depends(get_current_user_allow_pending),
) -> CurrentUser:
    """The gate every OTHER endpoint depends on -- mirrors
    auth.require_authenticated_user()'s hard stop on a pending forced
    password change.
    """
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "must_change_password",
                "message": "Debes establecer una contraseña nueva antes de continuar.",
            },
        )
    return user


def require_role(role: str):
    def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta acción requiere el rol '{role}'.",
            )
        return user

    return _checker


def require_any_role(roles: List[str]):
    def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta acción requiere alguno de estos roles: {', '.join(roles)}.",
            )
        return user

    return _checker
