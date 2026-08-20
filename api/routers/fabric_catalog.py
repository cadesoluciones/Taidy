# -*- coding: utf-8 -*-
"""
/fabric-catalog -- a documentation layer over the Fabric workspace's own
structure (notebooks, pipelines, lakehouses, ...), NOT another way to run or
manage anything (see src/fabric_pipelines for that). Structure is always
discovered live from the real Fabric API, same discipline and credentials
as /pipelines/{name}/dependencies; only the description/relationships an
admin or operator adds on top are persisted here.

"Catalogo de datos" (which this lives inside, as its own "Gobernanza de
datos" page) is Operator/Admin-only at the route level -- Reader never even
sees the nav entry. Gating this whole router the same way, not just the
write endpoint, means that's enforced here too, not just by the frontend
route guard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.fabric_pipelines.api import FabricPipelineClient, FabricPipelineError
from src.fabric_pipelines.config import load_settings
from webapp import fabric_catalog
from webapp.users_db import ROLE_ADMIN, ROLE_OPERATOR

from ..dependencies import CurrentUser, get_current_user, require_any_role
from ..schemas.fabric_catalog import (
    FabricCatalogListOut,
    FabricCatalogItemOut,
    UpdateFabricCatalogItemOut,
    UpdateFabricCatalogItemRequest,
)

router = APIRouter(
    prefix="/fabric-catalog",
    tags=["fabric-catalog"],
    dependencies=[Depends(require_any_role([ROLE_OPERATOR, ROLE_ADMIN]))],
)


def _client() -> FabricPipelineClient:
    try:
        settings = load_settings()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Fabric no está configurado: {exc}")
    return FabricPipelineClient(settings=settings)


@router.get("/items", response_model=FabricCatalogListOut)
def list_items() -> FabricCatalogListOut:
    try:
        items = fabric_catalog.list_catalog_items(_client())
    except FabricPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return FabricCatalogListOut(items=[FabricCatalogItemOut(**i) for i in items])


@router.patch("/items/{item_id}", response_model=UpdateFabricCatalogItemOut)
def update_item(
    item_id: str,
    payload: UpdateFabricCatalogItemRequest,
    current: CurrentUser = Depends(get_current_user),
) -> UpdateFabricCatalogItemOut:
    try:
        entry = fabric_catalog.set_metadata(
            item_id,
            short_description=payload.short_description,
            long_description_markdown=payload.long_description_markdown,
            owners=payload.owners,
            criticality=payload.criticality,
            status=payload.status,
            tags=payload.tags,
            relationships=[r.model_dump() for r in payload.relationships],
            reviewed_by=current.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return UpdateFabricCatalogItemOut(**entry)
