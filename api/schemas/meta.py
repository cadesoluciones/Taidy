# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class TableListOut(BaseModel):
    items: List[str]


class PipelineListOut(BaseModel):
    items: List[str]


class BcTableOut(BaseModel):
    name: str
    description: str = ""
    url: str
    incremental: bool = False


class BcTableListOut(BaseModel):
    items: List[BcTableOut]


class CreateBcTableRequest(BaseModel):
    name: str
    url: str
    description: str = ""
    incremental: bool = False


class UpdateBcTableRequest(BaseModel):
    url: str
    description: str = ""
    incremental: bool = False


class FactorialTableOut(BaseModel):
    name: str
    description: str = ""
    path: str
    fields: List[str]
    date_range: bool = True
    employee_filter: bool = True
    incremental: bool = False
    overlap_days: Optional[int] = None
    chunk_days: Optional[int] = None


class FactorialTableListOut(BaseModel):
    items: List[FactorialTableOut]


class CreateFactorialTableRequest(BaseModel):
    name: str
    path: str
    fields: List[str]
    description: str = ""
    date_range: bool = True
    employee_filter: bool = True
    incremental: bool = False
    overlap_days: Optional[int] = None
    chunk_days: Optional[int] = None


class UpdateFactorialTableRequest(BaseModel):
    path: str
    fields: List[str]
    description: str = ""
    date_range: bool = True
    employee_filter: bool = True
    incremental: bool = False
    overlap_days: Optional[int] = None
    chunk_days: Optional[int] = None


class HubspotTableOut(BaseModel):
    name: str
    description: str = ""
    object_type: str
    fields: List[str]


class HubspotTableListOut(BaseModel):
    items: List[HubspotTableOut]


class CreateHubspotTableRequest(BaseModel):
    name: str
    object_type: str
    fields: List[str]
    description: str = ""


class UpdateHubspotTableRequest(BaseModel):
    object_type: str
    fields: List[str]
    description: str = ""
