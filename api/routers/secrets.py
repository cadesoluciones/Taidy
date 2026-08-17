# -*- coding: utf-8 -*-
"""
/admin/secrets -- read/write access to .env's known keys (BC_CLIENT_SECRET,
HUBSPOT_API_KEY, ...) from the admin "Claves de servicio" screen, plus a
GET-only "probar acceso" check per service. Admin-only: this is the one
place in the app that returns real secret values to the browser, by
design (the UI pre-fills and masks them, with a per-field reveal toggle),
so it must never be reachable by Operator/Reader.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from webapp import env_secrets
from webapp.users_db import ROLE_ADMIN

from ..dependencies import get_current_user, require_role
from ..schemas.secrets import EnvFieldListOut, EnvFieldOut, TestConnectionOut, UpdateEnvFieldRequest

router = APIRouter(
    prefix="/admin/secrets",
    tags=["secrets"],
    dependencies=[Depends(get_current_user), Depends(require_role(ROLE_ADMIN))],
)


@router.get("", response_model=EnvFieldListOut)
def list_secrets() -> EnvFieldListOut:
    return EnvFieldListOut(items=[EnvFieldOut(**f) for f in env_secrets.list_fields()])


@router.patch("/{key}", response_model=EnvFieldOut)
def update_secret(key: str, payload: UpdateEnvFieldRequest) -> EnvFieldOut:
    try:
        field = env_secrets.set_field(key, payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return EnvFieldOut(**field)


@router.post("/test/business-central", response_model=TestConnectionOut)
def test_business_central() -> TestConnectionOut:
    return TestConnectionOut(**env_secrets.test_business_central())


@router.post("/test/factorial", response_model=TestConnectionOut)
def test_factorial() -> TestConnectionOut:
    return TestConnectionOut(**env_secrets.test_factorial())


@router.post("/test/hubspot", response_model=TestConnectionOut)
def test_hubspot() -> TestConnectionOut:
    return TestConnectionOut(**env_secrets.test_hubspot())


@router.post("/test/fabric", response_model=TestConnectionOut)
def test_fabric() -> TestConnectionOut:
    return TestConnectionOut(**env_secrets.test_fabric())
