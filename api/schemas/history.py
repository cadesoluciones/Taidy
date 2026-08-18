# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class HistoryEntryOut(BaseModel):
    action: str
    source: str
    status: str
    ok: bool
    message: str
    duration_seconds: Optional[float] = None
    finished_at: str
    log: str
    # Only populated for actions with a per-record breakdown (currently
    # sync_apply) -- absent/None for every other action's entries.
    details: Optional[List[Dict[str, Any]]] = None


class HistoryPageOut(BaseModel):
    items: List[HistoryEntryOut]
    total_matching: int
    total_available: int
    page: int
    page_size: int
    total_pages: int
