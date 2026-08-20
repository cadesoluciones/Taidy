# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List

from pydantic import BaseModel


class RelationshipIn(BaseModel):
    type: str  # "reads_from" | "writes_to" | "triggered_by"
    target_item_id: str


class RelationshipOut(BaseModel):
    type: str
    target_item_id: str


class FabricCatalogItemOut(BaseModel):
    item_id: str
    name: str
    type: str
    folder_path: List[str]
    short_description: str = ""
    long_description_markdown: str = ""
    owners: List[str] = []
    criticality: str = ""  # "" | "baja" | "media" | "alta"
    status: str = ""  # "" | "activo" | "en_desuso" | "deprecado"
    tags: List[str] = []
    relationships: List[RelationshipOut] = []
    reviewed_by: str = ""
    reviewed_at: str = ""


class FabricCatalogListOut(BaseModel):
    items: List[FabricCatalogItemOut]


class UpdateFabricCatalogItemRequest(BaseModel):
    short_description: str = ""
    long_description_markdown: str = ""
    owners: List[str] = []
    criticality: str = ""
    status: str = ""
    tags: List[str] = []
    relationships: List[RelationshipIn] = []


class UpdateFabricCatalogItemOut(BaseModel):
    short_description: str
    long_description_markdown: str
    owners: List[str]
    criticality: str
    status: str
    tags: List[str]
    relationships: List[RelationshipOut]
    reviewed_by: str
    reviewed_at: str
