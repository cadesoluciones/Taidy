# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List

from pydantic import BaseModel


class RecentRunOut(BaseModel):
    action: str
    source: str
    ok: bool
    status: str
    finished_at: str
    message: str


class DashboardSummaryOut(BaseModel):
    running_count: int
    active_schedule_count: int
    recent_error_count: int
    recent_history: List[RecentRunOut]
