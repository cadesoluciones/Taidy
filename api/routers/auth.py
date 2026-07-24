# -*- coding: utf-8 -*-
"""
Auth endpoints -- a thin wrapper around webapp/users_db.py and the same
audit log webapp/auth.py already writes to (webapp/audit.log), so both UIs
share one unified audit trail during the parallel-run period. No business
logic is reimplemented here: verify_login/change_password/get_user are the
exact same functions the Streamlit app calls.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from webapp import auth as webapp_auth
from webapp import users_db

from ..dependencies import (
    SESSION_COOKIE_NAME,
    CurrentUser,
    create_session,
    destroy_session,
    get_current_user_allow_pending,
)
from ..schemas.auth import ChangePasswordRequest, LoginRequest, UserSessionOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _secure_cookies() -> bool:
    """Only send the session cookie over HTTPS once behind a TLS-terminating
    reverse proxy (matching this project's existing loopback-only, proxy-
    fronted deployment model). Local dev over plain http needs this off.
    """
    return os.environ.get("TAIDY_API_SECURE_COOKIES", "false").lower() == "true"


@router.post("/login", response_model=UserSessionOut)
def login(payload: LoginRequest, response: Response) -> UserSessionOut:
    result = users_db.verify_login(payload.username, payload.password)
    if not result.ok:
        webapp_auth._audit("login", "denied", user=payload.username or "-", detail=result.reason)
        if result.reason.startswith("locked out"):
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=(
                    f"Cuenta bloqueada temporalmente tras {users_db.MAX_FAILED_ATTEMPTS} intentos "
                    "fallidos. Inténtalo de nuevo en unos minutos."
                ),
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos.")

    webapp_auth._audit("login", "ok", user=result.username)
    session_id = create_session(result.username)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
        path="/",
    )
    return UserSessionOut(username=result.username, role=result.role, must_change_password=result.must_change_password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    user: CurrentUser = Depends(get_current_user_allow_pending),
) -> None:
    webapp_auth._audit("logout", "ok", user=user.username)
    destroy_session(request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserSessionOut)
def me(user: CurrentUser = Depends(get_current_user_allow_pending)) -> UserSessionOut:
    return UserSessionOut(username=user.username, role=user.role, must_change_password=user.must_change_password)


@router.post("/change-password", response_model=UserSessionOut)
def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser = Depends(get_current_user_allow_pending),
) -> UserSessionOut:
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Las contraseñas no coinciden.")
    try:
        users_db.change_password(user.username, payload.new_password, must_change_password=False)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    webapp_auth._audit("password_change", "ok", user=user.username)
    updated = users_db.get_user(user.username)
    return UserSessionOut(
        username=updated["username"],
        role=updated["role"],
        must_change_password=bool(updated["must_change_password"]),
    )
