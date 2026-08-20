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
    AddRelationshipRequest,
    CanvasPositionsOut,
    CreateCustomFabricItemRequest,
    FabricCatalogListOut,
    FabricCatalogItemOut,
    FlagOut,
    SetCanvasPositionsRequest,
    SetFavoriteRequest,
    SetHiddenRequest,
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
            data_owner=payload.data_owner,
            data_steward=payload.data_steward,
            data_custodian=payload.data_custodian,
            data_consumer=payload.data_consumer,
            criticality=payload.criticality,
            status=payload.status,
            tags=payload.tags,
            relationships=[r.model_dump() for r in payload.relationships],
            reviewed_by=current.username,
            color=payload.color,
            icon=payload.icon,
            # Not passed: canvas_positions has its own save path (see
            # /canvas-positions below) and set_metadata() preserves the
            # existing value when it's omitted.
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return UpdateFabricCatalogItemOut(**entry)


@router.post("/custom-items", response_model=FabricCatalogItemOut)
def create_custom_item(
    payload: CreateCustomFabricItemRequest,
    current: CurrentUser = Depends(get_current_user),
) -> FabricCatalogItemOut:
    try:
        entry = fabric_catalog.create_custom_item(payload.name, payload.type, created_by=current.username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return FabricCatalogItemOut(**entry)


@router.delete("/custom-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_item(item_id: str) -> None:
    try:
        fabric_catalog.delete_custom_item(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/items/{item_id}/relationships", response_model=UpdateFabricCatalogItemOut)
def add_relationship(
    item_id: str,
    payload: AddRelationshipRequest,
    current: CurrentUser = Depends(get_current_user),
) -> UpdateFabricCatalogItemOut:
    """Used by the free-form relationship canvas: a connection drawn between
    two arbitrary blocks is saved immediately onto whichever one owns it,
    independent of whatever the item's own edit form might have open."""
    try:
        entry = fabric_catalog.add_relationship(
            item_id, payload.type, payload.target_item_id, reviewed_by=current.username
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return UpdateFabricCatalogItemOut(**entry)


@router.delete("/items/{item_id}/relationships", response_model=UpdateFabricCatalogItemOut)
def remove_relationship(
    item_id: str,
    type: str,
    target_item_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> UpdateFabricCatalogItemOut:
    try:
        entry = fabric_catalog.remove_relationship(item_id, type, target_item_id, reviewed_by=current.username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return UpdateFabricCatalogItemOut(**entry)


@router.put("/items/{item_id}/canvas-positions", response_model=CanvasPositionsOut)
def set_canvas_positions(item_id: str, payload: SetCanvasPositionsRequest) -> CanvasPositionsOut:
    try:
        entry = fabric_catalog.set_canvas_positions(item_id, {k: v.model_dump() for k, v in payload.positions.items()})
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CanvasPositionsOut(canvas_positions=entry["canvas_positions"])


@router.put("/items/{item_id}/favorite", response_model=FlagOut)
def set_favorite(item_id: str, payload: SetFavoriteRequest) -> FlagOut:
    entry = fabric_catalog.set_favorite(item_id, payload.is_favorite)
    return FlagOut(is_favorite=entry["is_favorite"], is_hidden=entry["is_hidden"])


@router.put("/items/{item_id}/hidden", response_model=FlagOut)
def set_hidden(item_id: str, payload: SetHiddenRequest) -> FlagOut:
    entry = fabric_catalog.set_hidden(item_id, payload.is_hidden)
    return FlagOut(is_favorite=entry["is_favorite"], is_hidden=entry["is_hidden"])
