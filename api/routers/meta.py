# -*- coding: utf-8 -*-
"""Read-only options for form dropdowns -- adapter.py's table/pipeline
lists, already mtime-cached there (Fase 9), so this is a cheap passthrough.

Also exposes add/delete over tables.yaml and factorial_tables.yaml
(webapp/table_configs.py) so new tables can be registered from the web UI
instead of hand-editing YAML on the server -- gated to Admin, same as any
other structural config change (create workflow, reset checkpoints)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from webapp import adapter, table_configs
from webapp.users_db import ROLE_ADMIN

from ..dependencies import get_current_user, require_role
from ..schemas.meta import (
    BcTableListOut,
    BcTableOut,
    CreateBcTableRequest,
    CreateFactorialTableRequest,
    FactorialTableListOut,
    FactorialTableOut,
    PipelineListOut,
    TableListOut,
    UpdateBcTableRequest,
    UpdateFactorialTableRequest,
)

router = APIRouter(prefix="/meta", tags=["meta"], dependencies=[Depends(get_current_user)])


@router.get("/bc-tables", response_model=TableListOut)
def bc_tables() -> TableListOut:
    return TableListOut(items=adapter.list_bc_tables())


@router.get("/factorial-tables", response_model=TableListOut)
def factorial_tables() -> TableListOut:
    return TableListOut(items=adapter.list_factorial_tables())


@router.get("/pipelines", response_model=PipelineListOut)
def pipelines() -> PipelineListOut:
    return PipelineListOut(items=adapter.list_fabric_pipelines())


@router.get("/bc-tables/full", response_model=BcTableListOut)
def bc_tables_full() -> BcTableListOut:
    return BcTableListOut(items=[BcTableOut(**t) for t in table_configs.list_bc_tables_full()])


@router.post("/bc-tables", response_model=BcTableOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def create_bc_table(payload: CreateBcTableRequest) -> BcTableOut:
    try:
        entry = table_configs.add_bc_table(
            payload.name, payload.url, description=payload.description, incremental=payload.incremental
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return BcTableOut(**entry)


@router.patch("/bc-tables/{name}", response_model=BcTableOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def update_bc_table(name: str, payload: UpdateBcTableRequest) -> BcTableOut:
    try:
        entry = table_configs.update_bc_table(
            name, payload.url, description=payload.description, incremental=payload.incremental
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return BcTableOut(**entry)


@router.delete(
    "/bc-tables/{name}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(ROLE_ADMIN))]
)
def delete_bc_table(name: str) -> None:
    table_configs.delete_bc_table(name)


@router.get("/factorial-tables/full", response_model=FactorialTableListOut)
def factorial_tables_full() -> FactorialTableListOut:
    return FactorialTableListOut(items=[FactorialTableOut(**t) for t in table_configs.list_factorial_tables_full()])


@router.post(
    "/factorial-tables", response_model=FactorialTableOut, dependencies=[Depends(require_role(ROLE_ADMIN))]
)
def create_factorial_table(payload: CreateFactorialTableRequest) -> FactorialTableOut:
    try:
        entry = table_configs.add_factorial_table(
            payload.name,
            payload.path,
            payload.fields,
            description=payload.description,
            date_range=payload.date_range,
            employee_filter=payload.employee_filter,
            incremental=payload.incremental,
            overlap_days=payload.overlap_days,
            chunk_days=payload.chunk_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return FactorialTableOut(**entry)


@router.patch(
    "/factorial-tables/{name}", response_model=FactorialTableOut, dependencies=[Depends(require_role(ROLE_ADMIN))]
)
def update_factorial_table(name: str, payload: UpdateFactorialTableRequest) -> FactorialTableOut:
    try:
        entry = table_configs.update_factorial_table(
            name,
            payload.path,
            payload.fields,
            description=payload.description,
            date_range=payload.date_range,
            employee_filter=payload.employee_filter,
            incremental=payload.incremental,
            overlap_days=payload.overlap_days,
            chunk_days=payload.chunk_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return FactorialTableOut(**entry)


@router.delete(
    "/factorial-tables/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(ROLE_ADMIN))],
)
def delete_factorial_table(name: str) -> None:
    table_configs.delete_factorial_table(name)
