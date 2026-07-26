# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List

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
