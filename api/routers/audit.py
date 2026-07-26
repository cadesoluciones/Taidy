# -*- coding: utf-8 -*-
"""GET /audit -- Admin only."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from webapp import auth as webapp_auth
from webapp.users_db import ROLE_ADMIN

from ..dependencies import require_role
from ..schemas.audit import AuditEntryOut, AuditPageOut
from ..services.audit_filters import filter_audit
from ..services.csv_export import csv_response

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_role(ROLE_ADMIN))])

_CSV_COLUMNS = [
    ("Fecha", "ts"),
    ("Evento", "event"),
    ("Resultado", "outcome"),
    ("Usuario", "user"),
    ("Detalle", "detail"),
]

# The UI table only ever shows the newest 200 (list_audit below); an export
# is expected to cover everything still retained across rotated backups
# (see webapp/auth.py's _MAX_AUDIT_BACKUPS), not just what's on screen.
_EXPORT_LIMIT = 100_000


@router.get("", response_model=AuditPageOut)
def list_audit(
    event: List[str] = Query(default=[]),
    user: List[str] = Query(default=[]),
    outcome: List[str] = Query(default=[]),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
) -> AuditPageOut:
    all_entries = webapp_auth.get_audit_log(200)
    matching, total = filter_audit(
        all_entries, events=event, users=user, outcomes=outcome, date_from=date_from, date_to=date_to
    )
    return AuditPageOut(
        items=[AuditEntryOut(**e) for e in matching],
        total_matching=total,
        total_available=len(all_entries),
    )


@router.get("/export.csv")
def export_audit_csv(
    event: List[str] = Query(default=[]),
    user: List[str] = Query(default=[]),
    outcome: List[str] = Query(default=[]),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
):
    """Same filters as GET /audit, but the full retained set as a CSV download."""
    all_entries = webapp_auth.get_audit_log(_EXPORT_LIMIT)
    matching, _total = filter_audit(
        all_entries, events=event, users=user, outcomes=outcome, date_from=date_from, date_to=date_to
    )
    return csv_response(matching, columns=_CSV_COLUMNS, filename="auditoria.csv")
