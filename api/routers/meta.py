# -*- coding: utf-8 -*-
"""Read-only options for form dropdowns -- adapter.py's table/pipeline
lists, already mtime-cached there (Fase 9), so this is a cheap passthrough."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from webapp import adapter

from ..dependencies import get_current_user
from ..schemas.meta import PipelineListOut, TableListOut

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
