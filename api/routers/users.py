# -*- coding: utf-8 -*-
"""
/users -- Admin only. Mirrors webapp/app.py:page_users exactly, including
the two invariants users_db.py itself enforces (never touched here, just
surfaced as HTTP 400s): the last admin can't be demoted or deleted.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from webapp import users_db

from .. import session_store
from ..dependencies import require_role
from ..schemas.users import (
    ChangeRoleRequest,
    CreateUserRequest,
    SessionListOut,
    SessionOut,
    UserListOut,
    UserOut,
)

router = APIRouter(prefix="/users", tags=["users"])


def _to_out(row: dict) -> UserOut:
    return UserOut(
        username=row["username"],
        role=row["role"],
        must_change_password=bool(row["must_change_password"]),
        locked_until=row.get("locked_until"),
    )


@router.get("", response_model=UserListOut, dependencies=[Depends(require_role(users_db.ROLE_ADMIN))])
def list_users() -> UserListOut:
    return UserListOut(items=[_to_out(u) for u in users_db.list_users()])


@router.post("", response_model=UserOut, dependencies=[Depends(require_role(users_db.ROLE_ADMIN))])
def create_user(payload: CreateUserRequest) -> UserOut:
    try:
        users_db.create_user(payload.username, payload.password, payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _to_out(users_db.get_user(payload.username.strip()))


@router.patch("/{username}/role", response_model=UserOut, dependencies=[Depends(require_role(users_db.ROLE_ADMIN))])
def change_role(username: str, payload: ChangeRoleRequest) -> UserOut:
    try:
        users_db.set_role(username, payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    row = users_db.get_user(username)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    return _to_out(row)


@router.post(
    "/{username}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(users_db.ROLE_ADMIN))],
)
def reset_password(username: str) -> None:
    users_db.force_password_reset(username)


@router.delete(
    "/{username}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(users_db.ROLE_ADMIN))]
)
def delete_user(username: str) -> None:
    try:
        users_db.delete_user(username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/{username}/sessions", response_model=SessionListOut, dependencies=[Depends(require_role(users_db.ROLE_ADMIN))]
)
def list_sessions(username: str) -> SessionListOut:
    return SessionListOut(items=[SessionOut(**s) for s in session_store.list_sessions_for_user(username)])


@router.delete(
    "/{username}/sessions/{session_ref}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(users_db.ROLE_ADMIN))],
)
def revoke_session(username: str, session_ref: str) -> None:
    session_store.revoke_session_by_ref(username, session_ref)
