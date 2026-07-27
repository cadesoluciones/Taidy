# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ScheduleOut(BaseModel):
    id: str
    name: str
    action: str
    params: Dict[str, Any]
    trigger: str
    trigger_args: Dict[str, Any]
    enabled: bool
    created_at: str
    next_run_time: Optional[str] = None
    missed_last_run: bool = False


class ScheduleListOut(BaseModel):
    items: List[ScheduleOut]


class CreateScheduleRequest(BaseModel):
    name: str
    action: str
    params: Dict[str, Any] = {}
    trigger: str  # "interval" | "cron"
    trigger_args: Dict[str, Any]


class SetScheduleEnabledRequest(BaseModel):
    enabled: bool


class ScheduleWeekOut(BaseModel):
    occurrences: Dict[str, List[str]]  # schedule_id -> ISO datetimes due this week
