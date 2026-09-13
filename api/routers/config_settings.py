# -*- coding: utf-8 -*-
"""
/admin/config -- read/write access to config.json's non-secret connection
parameters (tenant/client/workspace/lakehouse ids, retry/paging tuning,
notifications, Fabric pipeline mappings) from the admin "Claves de
servicio" screen. Admin-only, same as /admin/secrets it sits alongside --
these aren't secrets, but they're still real production identifiers
(tenant/workspace/lakehouse ids) an Operator/Reader has no business editing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from webapp import config_settings
from webapp.users_db import ROLE_ADMIN

from ..dependencies import get_current_user, require_role
from ..schemas.config_settings import (
    ConfigFieldListOut,
    ConfigFieldOut,
    PipelineListOut,
    PipelineOut,
    SetPipelinesRequest,
    UpdateConfigFieldRequest,
)

router = APIRouter(
    prefix="/admin/config",
    tags=["config-settings"],
    dependencies=[Depends(get_current_user), Depends(require_role(ROLE_ADMIN))],
)


@router.get("", response_model=ConfigFieldListOut)
def list_config_fields() -> ConfigFieldListOut:
    return ConfigFieldListOut(items=[ConfigFieldOut(**f) for f in config_settings.list_fields()])


@router.patch("/{key}", response_model=ConfigFieldOut)
def update_config_field(key: str, payload: UpdateConfigFieldRequest) -> ConfigFieldOut:
    try:
        field = config_settings.set_field(key, payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ConfigFieldOut(**field)


@router.get("/pipelines", response_model=PipelineListOut)
def list_pipelines() -> PipelineListOut:
    return PipelineListOut(items=[PipelineOut(**p) for p in config_settings.list_pipelines()])


@router.put("/pipelines", response_model=PipelineListOut)
def set_pipelines(payload: SetPipelinesRequest) -> PipelineListOut:
    try:
        items = config_settings.set_pipelines([p.model_dump() for p in payload.items])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return PipelineListOut(items=[PipelineOut(**p) for p in items])
