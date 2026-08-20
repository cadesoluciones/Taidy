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
    description: str = ""
    relationships: List[RelationshipOut] = []


class FabricCatalogListOut(BaseModel):
    items: List[FabricCatalogItemOut]


class UpdateFabricCatalogItemRequest(BaseModel):
    description: str = ""
    relationships: List[RelationshipIn] = []


class UpdateFabricCatalogItemOut(BaseModel):
    description: str
    relationships: List[RelationshipOut]
