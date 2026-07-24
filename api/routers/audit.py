# -*- coding: utf-8 -*-
"""GET /audit -- Admin only, mirrors webapp/app.py:page_audit."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from webapp import auth as webapp_auth
from webapp.users_db import ROLE_ADMIN

from ..dependencies import require_role
from ..schemas.audit import AuditEntryOut, AuditPageOut
from ..services.audit_filters import filter_audit

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_role(ROLE_ADMIN))])


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
