# -*- coding: utf-8 -*-
"""
Session store and FastAPI auth dependencies.

Never trust a cached client claim about role -- every request re-reads the
current role/must_change_password from users_db fresh; the session only
remembers WHO is asking, not what they're allowed to do.

Session persistence itself lives in api/session_store.py (a JSON file, not
an in-memory dict) so a server restart doesn't log out everyone -- see that
module's docstring.
"""

from __future__ import annotations

from typing import List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Cookie, Depends, HTTPException, Request, status

from webapp import auth as webapp_auth, users_db

from .session_store import create_session, destroy_session, get_session_username  # noqa: F401

SESSION_COOKIE_NAME = "taidy_session"


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
    """The gate every OTHER endpoint depends on -- hard-stops any request
    from a user with a pending forced password change.
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
            webapp_auth._audit("authorization", "denied", user=user.username, detail=f"missing role {role}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta acción requiere el rol '{role}'.",
            )
        return user

    return _checker


def require_any_role(roles: List[str]):
    def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            webapp_auth._audit("authorization", "denied", user=user.username, detail=f"missing any of {roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta acción requiere alguno de estos roles: {', '.join(roles)}.",
            )
        return user

    return _checker


def get_scheduler(request: Request) -> BackgroundScheduler:
    """The live APScheduler instance, created once in main.py's lifespan hook --
    schedules.py's add/remove/enable functions need the live object, not just
    the JSON file.
    """
    return request.app.state.scheduler
