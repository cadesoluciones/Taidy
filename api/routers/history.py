# -*- coding: utf-8 -*-
"""GET /history -- Fase 6 ND-08 filters + pagination, ported from
webapp/app.py:page_history."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from webapp import history as history_module

from ..dependencies import get_current_user
from ..schemas.history import HistoryEntryOut, HistoryPageOut
from ..services.csv_export import csv_response
from ..services.history_filters import RESULT_ALL, filter_and_paginate, filter_only

router = APIRouter(prefix="/history", tags=["history"], dependencies=[Depends(get_current_user)])

_CSV_COLUMNS = [
    ("Fecha", "finished_at"),
    ("Acción", "action"),
    ("Origen", "source"),
    ("Resultado", "status_label"),
    ("Duración (s)", "duration_seconds"),
    ("Mensaje", "message"),
    ("Log", "log"),
]

_STATUS_LABELS = {"ok": "Correcto", "error": "Error", "stopped": "Detenida"}


@router.get("", response_model=HistoryPageOut)
def list_history(
    action: List[str] = Query(default=[]),
    source: List[str] = Query(default=[]),
    result: str = Query(default=RESULT_ALL),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> HistoryPageOut:
    all_entries = history_module.get_history(limit=200)
    page_items, total_matching = filter_and_paginate(
        all_entries,
        actions=action,
        sources=source,
        result=result,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total_matching + page_size - 1) // page_size)
    return HistoryPageOut(
        items=[HistoryEntryOut(**e) for e in page_items],
        total_matching=total_matching,
        total_available=len(all_entries),
        page=min(max(page, 1), total_pages),
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/export.csv")
def export_history_csv(
    action: List[str] = Query(default=[]),
    source: List[str] = Query(default=[]),
    result: str = Query(default=RESULT_ALL),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
):
    """Same filters as GET /history, but the full matching set (not one
    page) as a CSV download."""
    all_entries = history_module.get_history(limit=200)
    matching = filter_only(all_entries, actions=action, sources=source, result=result, date_from=date_from, date_to=date_to)
    rows = [{**e, "status_label": _STATUS_LABELS.get(e["status"], e["status"])} for e in matching]
    return csv_response(rows, columns=_CSV_COLUMNS, filename="historial.csv")
