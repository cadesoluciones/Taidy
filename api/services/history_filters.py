# -*- coding: utf-8 -*-
"""
Filter/paginate logic ported verbatim from webapp/app.py:page_history's
_matches() closure (Fase 6 ND-08) -- kept here as a plain, unit-testable
function so the API and any future caller share one implementation instead
of each re-deriving the filter semantics.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence, Tuple

RESULT_ALL = "all"
RESULT_OK = "ok"
RESULT_ERROR = "error"
RESULT_STOPPED = "stopped"


def _matches(
    entry: dict,
    *,
    actions: Sequence[str],
    sources: Sequence[str],
    result: str,
    date_from,
    date_to,
) -> bool:
    if actions and entry["action"] not in actions:
        return False
    if sources and entry["source"] not in sources:
        return False
    if result == RESULT_OK and not entry["ok"]:
        return False
    if result == RESULT_ERROR and (entry["ok"] or entry.get("status") == "stopped"):
        return False
    if result == RESULT_STOPPED and entry.get("status") != "stopped":
        return False
    if date_from or date_to:
        entry_date = datetime.fromisoformat(entry["finished_at"]).date()
        if date_from and entry_date < date_from:
            return False
        if date_to and entry_date > date_to:
            return False
    return True


def filter_and_paginate(
    entries: List[dict],
    *,
    actions: Sequence[str] = (),
    sources: Sequence[str] = (),
    result: str = RESULT_ALL,
    date_from=None,
    date_to=None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[dict], int]:
    """Returns (page of matching entries, total matching count)."""
    matching = [
        e for e in entries if _matches(e, actions=actions, sources=sources, result=result, date_from=date_from, date_to=date_to)
    ]
    total_pages = max(1, (len(matching) + page_size - 1) // page_size)
    page = min(max(page, 1), total_pages)
    start = (page - 1) * page_size
    return matching[start : start + page_size], len(matching)
