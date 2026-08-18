# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SystemRef(BaseModel):
    system: str
    table: str


class FieldPair(BaseModel):
    source: str
    target: str


class RowFilter(BaseModel):
    field: str
    equals: str


class SyncMappingOut(BaseModel):
    name: str
    description: str = ""
    source: SystemRef
    target: SystemRef
    matching_key: FieldPair
    date_field: FieldPair
    fields: List[FieldPair]
    source_filter: Optional[RowFilter] = None
    target_filter: Optional[RowFilter] = None


class SyncMappingListOut(BaseModel):
    items: List[SyncMappingOut]


class CreateSyncMappingRequest(BaseModel):
    name: str
    source: SystemRef
    target: SystemRef
    matching_key: FieldPair
    date_field: FieldPair
    fields: List[FieldPair]
    description: str = ""
    source_filter: Optional[RowFilter] = None
    target_filter: Optional[RowFilter] = None


class UpdateSyncMappingRequest(BaseModel):
    name: str
    source: SystemRef
    target: SystemRef
    matching_key: FieldPair
    date_field: FieldPair
    fields: List[FieldPair]
    description: str = ""
    source_filter: Optional[RowFilter] = None
    target_filter: Optional[RowFilter] = None


class RecordActionOut(BaseModel):
    key: str
    kind: str
    source_row: Optional[Dict[str, Any]] = None
    target_row: Optional[Dict[str, Any]] = None
    source_date: Optional[str] = None
    target_date: Optional[str] = None


class SkippedRecordOut(BaseModel):
    system: str
    reason: str
    key: str
    row: Dict[str, Any]


class ComparisonReportOut(BaseModel):
    mapping_name: str
    create_in_target: List[RecordActionOut]
    create_in_source: List[RecordActionOut]
    update_target: List[RecordActionOut]
    update_source: List[RecordActionOut]
    unchanged: List[RecordActionOut]
    skipped: List[SkippedRecordOut]
