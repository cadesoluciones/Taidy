# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel


class RelationshipIn(BaseModel):
    type: str  # "reads_from" | "writes_to" | "triggered_by" | "generates" | "updates"
    target_item_id: str


class RelationshipOut(BaseModel):
    type: str
    target_item_id: str


class PositionIn(BaseModel):
    x: float
    y: float


class PositionOut(BaseModel):
    x: float
    y: float


class FabricCatalogItemOut(BaseModel):
    item_id: str
    name: str
    type: str
    folder_path: List[str]
    short_description: str = ""
    long_description_markdown: str = ""
    data_owner: List[str] = []
    data_steward: List[str] = []
    data_custodian: List[str] = []
    data_consumer: List[str] = []
    criticality: str = ""  # "" | "baja" | "media" | "alta"
    status: str = ""  # "" | "activo" | "en_desuso" | "deprecado"
    tags: List[str] = []
    relationships: List[RelationshipOut] = []
    reviewed_by: str = ""
    reviewed_at: str = ""
    is_custom: bool = False
    color: str = ""
    icon: str = ""
    canvas_positions: Dict[str, PositionOut] = {}
    is_favorite: bool = False
    is_hidden: bool = False
    # "online": seen in Fabric's own response this call. "offline": not seen
    # this call (Fabric outage, or its capacity/license lapsed) -- served
    # from the last successful sighting instead of just disappearing, see
    # webapp/fabric_catalog_cache.py. Always "online" for BC/HubSpot/
    # Factorial/custom items -- they're never Fabric-discovered. Not on
    # UpdateFabricCatalogItemOut below on purpose: editing metadata never
    # changes this, and the frontend's patch-merge would otherwise stomp a
    # real "offline" back to the field's own default "online" on every save.
    connection_status: str = "online"
    last_synced_at: str = ""


class FabricCatalogListOut(BaseModel):
    items: List[FabricCatalogItemOut]


class UpdateFabricCatalogItemRequest(BaseModel):
    short_description: str = ""
    long_description_markdown: str = ""
    data_owner: List[str] = []
    data_steward: List[str] = []
    data_custodian: List[str] = []
    data_consumer: List[str] = []
    criticality: str = ""
    status: str = ""
    tags: List[str] = []
    relationships: List[RelationshipIn] = []
    color: str = ""
    icon: str = ""


class CreateCustomFabricItemRequest(BaseModel):
    name: str
    type: str = ""


class UpdateFabricCatalogItemOut(BaseModel):
    short_description: str
    long_description_markdown: str
    data_owner: List[str]
    data_steward: List[str]
    data_custodian: List[str]
    data_consumer: List[str]
    criticality: str
    status: str
    tags: List[str]
    relationships: List[RelationshipOut]
    reviewed_by: str
    reviewed_at: str
    color: str = ""
    icon: str = ""
    canvas_positions: Dict[str, PositionOut] = {}
    is_favorite: bool = False
    is_hidden: bool = False


class AddRelationshipRequest(BaseModel):
    type: str
    target_item_id: str


class SetCanvasPositionsRequest(BaseModel):
    positions: Dict[str, PositionIn]


class CanvasPositionsOut(BaseModel):
    canvas_positions: Dict[str, PositionOut] = {}


class SetFavoriteRequest(BaseModel):
    is_favorite: bool


class SetHiddenRequest(BaseModel):
    is_hidden: bool


class FlagOut(BaseModel):
    is_favorite: bool
    is_hidden: bool


class TablePreviewOut(BaseModel):
    columns: List[str]
    rows: List[List[str]]


class SemanticModelColumnOut(BaseModel):
    name: str
    description: str = ""
    data_type: str = ""
    in_source: bool = True


class SemanticModelStateOut(BaseModel):
    linked: bool
    model_item_id: str = ""
    model_name: str = ""
    columns: List[SemanticModelColumnOut] = []
    # Real source-table columns the model doesn't have yet (schema drift, or
    # not-yet-linked) -- drives the "sync columns" button. Always empty for
    # a manual (has_real_source: false) model -- nothing to sync against.
    missing_columns: List[str] = []
    # Whether this item has a real, queryable table behind it (a Lakehouse
    # table -- DirectLake, auto-detected columns) or not (BC/HubSpot/
    # Factorial/custom -- manual columns, no live data connection). Tells
    # the frontend which editing UI to show.
    has_real_source: bool = False


class ManualColumnIn(BaseModel):
    name: str
    data_type: str  # one of src.fabric_pipelines.semantic_model_tmdl.MANUAL_DATA_TYPES


class UpdateSemanticModelDescriptionsRequest(BaseModel):
    descriptions: Dict[str, str]


class CreateSemanticModelRequest(BaseModel):
    # Both ignored for a Lakehouse table (columns always auto-detected).
    # Both required for anything else -- item_name is the catalog item's
    # own display name (this module has no independent way to look it up).
    item_name: str = ""
    columns: List[ManualColumnIn] = []


class SetManualSemanticModelColumnsRequest(BaseModel):
    columns: List[ManualColumnIn]


class SuggestedColumnOut(BaseModel):
    name: str
    data_type: str  # "string" unless the source system exposes a real type -- see suggest_manual_columns()


class SuggestedColumnsOut(BaseModel):
    columns: List[SuggestedColumnOut]


class CatalogManifestColumnOut(BaseModel):
    name: str
    data_type: str = ""
    description: str = ""
    example: str = ""


class CatalogManifestOut(BaseModel):
    table_description: str = ""
    columns: List[CatalogManifestColumnOut] = []
    # False: no catalog_manifests/<table>.yml exists yet -- `columns` was
    # seeded from the real table schema instead, nothing saved yet.
    has_manifest: bool = False


class CatalogManifestColumnIn(BaseModel):
    name: str
    data_type: str = ""
    description: str = ""
    example: str = ""


class SetCatalogManifestRequest(BaseModel):
    table_description: str = ""
    columns: List[CatalogManifestColumnIn]


class TypeIconsOut(BaseModel):
    icons: Dict[str, str]


class SetTypeIconRequest(BaseModel):
    type: str
    # "" clears the override, falling back to the built-in default (or none).
    icon: str = ""
