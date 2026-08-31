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
    in_source: bool = True


class SemanticModelStateOut(BaseModel):
    linked: bool
    model_item_id: str = ""
    model_name: str = ""
    columns: List[SemanticModelColumnOut] = []
    # Real source-table columns the model doesn't have yet (schema drift, or
    # not-yet-linked) -- drives the "sync columns" button.
    missing_columns: List[str] = []


class UpdateSemanticModelDescriptionsRequest(BaseModel):
    descriptions: Dict[str, str]


class TypeIconsOut(BaseModel):
    icons: Dict[str, str]


class SetTypeIconRequest(BaseModel):
    type: str
    # "" clears the override, falling back to the built-in default (or none).
    icon: str = ""
