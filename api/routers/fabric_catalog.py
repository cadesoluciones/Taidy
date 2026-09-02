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
from webapp import app_settings, fabric_catalog
from webapp.users_db import ROLE_ADMIN, ROLE_OPERATOR

from ..dependencies import CurrentUser, get_current_user, require_any_role, require_role
from ..schemas.fabric_catalog import (
    AddRelationshipRequest,
    CanvasPositionsOut,
    CatalogManifestOut,
    CreateCustomFabricItemRequest,
    CreateSemanticModelRequest,
    FabricCatalogListOut,
    FabricCatalogItemOut,
    FlagOut,
    SemanticModelStateOut,
    SetCatalogManifestRequest,
    SetCanvasPositionsRequest,
    SetFavoriteRequest,
    SetHiddenRequest,
    SetManualSemanticModelColumnsRequest,
    SetTypeIconRequest,
    SuggestedColumnOut,
    SuggestedColumnsOut,
    TablePreviewOut,
    TypeIconsOut,
    UpdateFabricCatalogItemOut,
    UpdateFabricCatalogItemRequest,
    UpdateSemanticModelDescriptionsRequest,
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


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offline_item(item_id: str) -> None:
    """Forgets a Fabric-discovered item's local cache entry + governance
    metadata -- only for an item currently "sin conexión" (see
    connection_status on GET /items). Never touches Fabric itself; if the
    real item still exists there and Fabric lists it again later, it just
    reappears. 400 for a BC/HubSpot/Factorial/custom item (always online,
    this doesn't apply) or one not in the catalog at all."""
    try:
        fabric_catalog.delete_offline_item(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


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


@router.get("/items/{item_id}/preview", response_model=TablePreviewOut)
def preview_table(item_id: str) -> TablePreviewOut:
    """`SELECT TOP 10 *` against the real Lakehouse table a
    "lakehouse-table:..." catalog item stands for -- just to see its
    columns and a few sample rows, not a general query tool. 400 for any
    item this doesn't apply to (only Lakehouse tables are SQL-queryable);
    502 if Fabric/the SQL endpoint can't actually be reached right now."""
    try:
        result = fabric_catalog.preview_lakehouse_table(_client(), item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FabricPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return TablePreviewOut(**result)


@router.get("/items/{item_id}/catalog-manifest", response_model=CatalogManifestOut)
def get_catalog_manifest(item_id: str) -> CatalogManifestOut:
    """This Lakehouse table's catalog_manifests/<table>.yml -- the data
    contract a `catalog_metadata` notebook in this workspace reads to
    (re)generate a matching catalog.<table> Delta table from. `has_manifest:
    false` means no manifest exists yet, so `columns` is seeded from the
    real table schema instead. 400 for anything that isn't a Lakehouse
    table (there's no manifest concept for those); 502 if Fabric/OneLake
    can't be reached right now."""
    try:
        result = fabric_catalog.get_catalog_manifest(_client(), item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FabricPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return CatalogManifestOut(**result)


@router.put("/items/{item_id}/catalog-manifest", response_model=CatalogManifestOut)
def set_catalog_manifest(item_id: str, payload: SetCatalogManifestRequest) -> CatalogManifestOut:
    """Overwrites catalog_manifests/<table>.yml wholesale (never the
    catalog.<table> Delta table itself -- a notebook run would just discard
    an edit made there). 400 for anything that isn't a Lakehouse table, no
    columns, a blank/duplicate column name; 502 for a real OneLake failure."""
    try:
        result = fabric_catalog.set_catalog_manifest(
            _client(), item_id, table_description=payload.table_description, columns=[c.model_dump() for c in payload.columns]
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FabricPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return CatalogManifestOut(**result)


@router.get("/items/{item_id}/suggested-columns", response_model=SuggestedColumnsOut)
def suggested_columns(item_id: str) -> SuggestedColumnsOut:
    """Best-effort starting point for a manual semantic model's column
    builder -- see fabric_catalog.suggest_manual_columns() for exactly what
    each system (HubSpot/Factorial/BC) can offer; [] for anything else
    (nothing to suggest). 400 for a HubSpot configuration problem (e.g.
    missing credentials); 502 if the live HubSpot call itself fails."""
    from src.hubspot_client.api import HubspotError

    try:
        columns = fabric_catalog.suggest_manual_columns(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except HubspotError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return SuggestedColumnsOut(columns=[SuggestedColumnOut(**c) for c in columns])


@router.get("/items/{item_id}/semantic-model", response_model=SemanticModelStateOut)
def get_semantic_model(item_id: str) -> SemanticModelStateOut:
    """Live state of the item's linked Fabric semantic model (or the
    "not linked yet" state -- for a Lakehouse table, every real column is
    listed as missing so the tab can offer "crear" pre-populated). Works
    for any catalog item type, not just Lakehouse tables -- see
    `has_real_source` in the response for which editing mode applies.
    502 if Fabric/the SQL endpoint can't be reached right now."""
    try:
        result = fabric_catalog.get_semantic_model_state(_client(), item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FabricPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return SemanticModelStateOut(**result)


@router.post("/items/{item_id}/semantic-model", response_model=SemanticModelStateOut)
def create_semantic_model(item_id: str, payload: CreateSemanticModelRequest) -> SemanticModelStateOut:
    """Creates a new single-table semantic model for this catalog item and
    links it. For a Lakehouse table, columns are always auto-detected from
    its real schema (`payload` is ignored even if it carries columns) --
    the reliable path. For anything else, `payload.item_name` (the item's
    own display name -- there's no way to look it up server-side for a
    BC/HubSpot/Factorial/custom item) and at least one manually typed
    column in `payload.columns` are required: the result has no live data
    connection, just documented column names/types/descriptions.
    400 if a model's already linked, the Lakehouse table has no columns to
    detect, or (for a manual model) item_name/columns is missing; 502 for a
    real Fabric-side failure."""
    try:
        result = fabric_catalog.create_semantic_model(
            _client(),
            item_id,
            item_name=payload.item_name,
            columns=[c.model_dump() for c in payload.columns],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FabricPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return SemanticModelStateOut(**result)


@router.patch("/items/{item_id}/semantic-model", response_model=SemanticModelStateOut)
def update_semantic_model(item_id: str, payload: UpdateSemanticModelDescriptionsRequest) -> SemanticModelStateOut:
    """Pushes column description edits to the linked semantic model."""
    try:
        result = fabric_catalog.update_semantic_model_descriptions(_client(), item_id, payload.descriptions)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FabricPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return SemanticModelStateOut(**result)


@router.post("/items/{item_id}/semantic-model/sync-columns", response_model=SemanticModelStateOut)
def sync_semantic_model_columns(item_id: str) -> SemanticModelStateOut:
    """Adds any column the real source table has that the linked semantic
    model doesn't yet (auto-detected schema drift) -- see
    fabric_catalog.sync_semantic_model_columns()."""
    try:
        result = fabric_catalog.sync_semantic_model_columns(_client(), item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FabricPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return SemanticModelStateOut(**result)


@router.put("/items/{item_id}/semantic-model/columns", response_model=SemanticModelStateOut)
def set_manual_semantic_model_columns(
    item_id: str, payload: SetManualSemanticModelColumnsRequest
) -> SemanticModelStateOut:
    """Replaces a manual (no real data source) model's full column list --
    used to add or remove a column, since its DATATABLE() partition has to
    declare every column in lockstep. 400 for a Lakehouse table (its
    columns are auto-detected, see sync-columns above instead), no linked
    model, or an unknown data type."""
    try:
        result = fabric_catalog.set_manual_semantic_model_columns(
            _client(), item_id, [c.model_dump() for c in payload.columns]
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except FabricPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return SemanticModelStateOut(**result)


@router.get("/type-icons", response_model=TypeIconsOut)
def get_type_icons() -> TypeIconsOut:
    """The default icon (see ICON_KEYS) shown for each catalog item type
    when an item hasn't had one set by hand -- built-in defaults plus
    whatever an admin has overridden in Configuración."""
    return TypeIconsOut(icons=app_settings.get_type_icons())


@router.put("/type-icons", response_model=TypeIconsOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def set_type_icon(payload: SetTypeIconRequest) -> TypeIconsOut:
    try:
        icons = app_settings.set_type_icon(payload.type, payload.icon, valid_icon_keys=fabric_catalog.ICON_KEYS)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return TypeIconsOut(icons=icons)
