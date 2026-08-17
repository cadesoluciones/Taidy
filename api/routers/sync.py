# -*- coding: utf-8 -*-
"""
/sync/mappings -- field-level mappings for reconciling records between two
already-configured tables, and /sync/mappings/{name}/compare -- a read-only
preview of what a real sync would do (Fase 1 of the BC<->HubSpot contact
sync). Nothing here ever writes to BC/HubSpot: "compare" only reads both
sides live and reports planned actions; the write path is a later phase.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.sync_engine.compare import SyncCompareError, compare_mapping
from webapp import sync_mappings
from webapp.users_db import ROLE_ADMIN, ROLE_OPERATOR

from ..dependencies import CurrentUser, get_current_user, require_role
from ..schemas.sync import (
    ComparisonReportOut,
    CreateSyncMappingRequest,
    RecordActionOut,
    SkippedRecordOut,
    SyncMappingListOut,
    SyncMappingOut,
    UpdateSyncMappingRequest,
)

router = APIRouter(prefix="/sync", tags=["sync"], dependencies=[Depends(get_current_user)])

_ROLES_OPERATE = [ROLE_OPERATOR, ROLE_ADMIN]


@router.get("/mappings", response_model=SyncMappingListOut)
def list_mappings() -> SyncMappingListOut:
    return SyncMappingListOut(items=[SyncMappingOut(**m) for m in sync_mappings.list_mappings_full()])


@router.post("/mappings", response_model=SyncMappingOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def create_mapping(payload: CreateSyncMappingRequest) -> SyncMappingOut:
    try:
        entry = sync_mappings.add_mapping(
            payload.name,
            payload.source.model_dump(),
            payload.target.model_dump(),
            payload.matching_key.model_dump(),
            payload.date_field.model_dump(),
            [f.model_dump() for f in payload.fields],
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return SyncMappingOut(**entry)


@router.patch("/mappings/{name}", response_model=SyncMappingOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def update_mapping(name: str, payload: UpdateSyncMappingRequest) -> SyncMappingOut:
    try:
        entry = sync_mappings.update_mapping(
            name,
            payload.source.model_dump(),
            payload.target.model_dump(),
            payload.matching_key.model_dump(),
            payload.date_field.model_dump(),
            [f.model_dump() for f in payload.fields],
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return SyncMappingOut(**entry)


@router.delete(
    "/mappings/{name}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(ROLE_ADMIN))]
)
def delete_mapping(name: str) -> None:
    sync_mappings.delete_mapping(name)


@router.post("/mappings/{name}/compare", response_model=ComparisonReportOut)
def compare(name: str, current: CurrentUser = Depends(get_current_user)) -> ComparisonReportOut:
    if current.role not in _ROLES_OPERATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Comparar requiere rol App.Operator o App.Admin.",
        )
    try:
        report = compare_mapping(name)
    except SyncCompareError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return ComparisonReportOut(
        mapping_name=report.mapping_name,
        create_in_target=[RecordActionOut(**vars(a)) for a in report.create_in_target],
        create_in_source=[RecordActionOut(**vars(a)) for a in report.create_in_source],
        update_target=[RecordActionOut(**vars(a)) for a in report.update_target],
        update_source=[RecordActionOut(**vars(a)) for a in report.update_source],
        unchanged=[RecordActionOut(**vars(a)) for a in report.unchanged],
        skipped=[SkippedRecordOut(**vars(s)) for s in report.skipped],
    )
