# -*- coding: utf-8 -*-
"""Filter logic ported from webapp/app.py:page_audit's _matches() closure."""

from __future__ import annotations

from datetime import datetime
from typing import List, Sequence, Tuple


def filter_audit(
    entries: List[dict],
    *,
    events: Sequence[str] = (),
    users: Sequence[str] = (),
    outcomes: Sequence[str] = (),
    date_from=None,
    date_to=None,
) -> Tuple[List[dict], int]:
    def _matches(e: dict) -> bool:
        if events and e.get("event", "") not in events:
            return False
        if users and e.get("user", "") not in users:
            return False
        if outcomes and e.get("outcome", "") not in outcomes:
            return False
        if date_from or date_to:
            ts = e.get("ts", "")
            if not ts:
                return False
            entry_date = datetime.fromisoformat(ts).date()
            if date_from and entry_date < date_from:
                return False
            if date_to and entry_date > date_to:
                return False
        return True

    matching = [e for e in entries if _matches(e)]
    return matching, len(matching)
